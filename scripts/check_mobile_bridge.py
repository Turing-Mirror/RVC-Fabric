"""Exercise a running desktop instance through its existing local API.

Developer dependency: aiohttp. No soundcard is opened by this check.
Generated invitations and credentials stay in the explicitly supplied output directory.
"""
import argparse
import asyncio
import array
import json
import math
import io
import wave
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import aiohttp


async def rpc(session, record, method, params):
    async with session.ws_connect(record['endpoint'], headers={'Authorization': 'Bearer ' + record['token']}) as ws:
        await ws.send_json({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
        async for message in ws:
            value = json.loads(message.data)
            if value.get('id') == 1:
                if 'error' in value:
                    raise RuntimeError(value['error'])
                return value['result']
        raise RuntimeError('local API closed')


async def main(args):
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = [json.loads(p.read_text()) for p in Path(args.registry).joinpath('apps').glob('*.json')]
    assert len(records) == 1, 'Use the isolated test registry containing one desktop instance'
    record = records[0]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=240)) as session:
        async def invoke(command, **kwargs):
            return await rpc(session, record, 'ui.invoke', {'command': command, 'args': kwargs})
        if args.show:
            await rpc(session, record, 'app.show', {})
            return
        if args.quit:
            await rpc(session, record, 'app.quit', {})
            return
        before = await invoke('mobile_status')
        invitation = await invoke('mobile_pairing', host=args.host)
        out.joinpath('invitation.json').write_text(json.dumps(invitation), encoding='utf-8')
        print(json.dumps({'enabled_before': before['enabled'], 'endpoint': invitation['endpoint']}, ensure_ascii=False), flush=True)
        if args.invite_only:
            return
        payload = json.loads(parse_qs(urlparse(invitation['payload']).query)['data'][0])
        endpoint = payload['endpoint']
        async with session.get(endpoint + '/v1/health') as response:
            assert response.status == 401
        request = {'ticket': payload['ticket'], 'device_id': 'integration-test', 'name': 'Mobile integration check'}
        async with session.post(endpoint + '/v1/pair', json=request) as response:
            assert response.status == 200, await response.text()
            credential = await response.json()
        async with session.post(endpoint + '/v1/pair', json=request) as response:
            assert response.status == 400
        headers = {'Authorization': 'Bearer ' + credential['token']}
        frames, nonzero, peaks, proc = 0, 0, [], []
        latest = {}
        pending = {}
        sequence = 0
        async with session.ws_connect(endpoint + '/v1/ws', headers=headers) as ws:
            welcome = await ws.receive_json()
            assert welcome['type'] == 'welcome', welcome
            assert welcome['voices'], 'No test voice installed'
            print(json.dumps({'voices': len(welcome['voices']), 'capabilities': welcome['capabilities']}), flush=True)
            if args.media_only:
                async def drain():
                    async for _ in ws:
                        pass
                draining = asyncio.create_task(drain())
                buffer=io.BytesIO()
                with wave.open(buffer,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
                    wav.writeframes(array.array('h',(int(3000*math.sin(i*2*math.pi*180/48000)) for i in range(48000*3))).tobytes())
                async with session.post(endpoint+'/v1/uploads',headers=headers,data=buffer.getvalue()) as response:
                    assert response.status==200,await response.text()
                    uploaded=await response.json()
                async with session.post(endpoint+'/v1/jobs',headers=headers,json={'file':uploaded['file'],'voices':[welcome['voices'][0]['id']],'pitch':0}) as response:
                    assert response.status==200,await response.text()
                    job=await response.json()
                deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    # Keep the authenticated mobile session alive during the file job.
                    await ws.ping()
                    async with session.get(endpoint+'/v1/jobs/'+job['id'],headers=headers) as response:
                        result=await response.json()
                    if result['state'] not in ('queued','running'): break
                    await asyncio.sleep(1)
                assert result['state']=='done',result
                assert result['progress']==1 and len(result['results'])==1,result
                for item in [result['original'],result['results'][0]['file']]:
                    async with session.get(endpoint+'/v1/files/'+item,headers=headers) as response:
                        assert response.status==200
                        data=await response.read()
                    assert data[:4]==b'RIFF' and len(data)>1024
                    out.joinpath(item).write_bytes(data)
                print('REAL_FILE_CONVERSION_OK',flush=True)
                out.joinpath('media-report.json').write_text(json.dumps(result,indent=2))
                async with session.post(endpoint+'/v1/jobs',headers=headers,json={'file':uploaded['file'],'voices':[welcome['voices'][0]['id']],'pitch':0}) as response:
                    assert response.status==200,await response.text()
                    cancelled=await response.json()
                async with session.delete(endpoint+'/v1/jobs/'+cancelled['id'],headers=headers) as response:
                    assert response.status==200
                for _ in range(30):
                    async with session.get(endpoint+'/v1/jobs/'+cancelled['id'],headers=headers) as response:
                        cancelled=await response.json()
                    if cancelled['state'] not in ('queued','running'): break
                    await ws.ping();await asyncio.sleep(.5)
                assert cancelled['state']=='cancelled',cancelled
                extra=await invoke('mobile_pairing',host=args.host)
                extra_payload=json.loads(parse_qs(urlparse(extra['payload']).query)['data'][0])
                async with session.post(endpoint+'/v1/pair',json={'ticket':extra_payload['ticket'],'device_id':'isolation-test','name':'Isolation check'}) as response:
                    assert response.status==200
                    other=await response.json()
                other_headers={'Authorization':'Bearer '+other['token']}
                for path in ['/v1/jobs/'+result['id'],'/v1/files/'+result['original']]:
                    async with session.get(endpoint+path,headers=other_headers) as response:
                        assert response.status==404
                await invoke('mobile_action',action={'type':'revoke','id':'isolation-test'})
                await invoke('mobile_action',action={'type':'revoke','id':'integration-test'})
                draining.cancel();await asyncio.gather(draining,return_exceptions=True)
                print('FILE_CANCEL_AND_DEVICE_ISOLATION_OK',flush=True)
                return
            async def receive():
                nonlocal frames, nonzero, latest
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        assert len(msg.data) == 1920
                        samples = array.array('h', msg.data)
                        peak = max(abs(s) for s in samples)
                        frames += 1
                        if peak:
                            nonzero += 1
                            peaks.append(peak)
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        value = json.loads(msg.data)
                        if value.get('type') == 'status':
                            latest = value
                            if value.get('proc_ms') is not None:
                                proc.append(value['proc_ms'])
                        future = pending.pop(value.get('request_id'), None)
                        if future is not None and not future.done():
                            if value.get('type') == 'error': future.set_exception(RuntimeError(value))
                            else: future.set_result(value)
            reader = asyncio.create_task(receive())
            async def command(kind, **data):
                nonlocal sequence
                sequence += 1
                key = str(sequence)
                future = asyncio.get_running_loop().create_future()
                pending[key] = future
                await ws.send_json(dict(data, type=kind, request_id=key))
                return await asyncio.wait_for(future, 190)
            if args.clips:
                clip_path=out/'clip.wav'
                with wave.open(str(clip_path),'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
                    wav.writeframes(array.array('h',(int(2500*math.sin(i*2*math.pi*440/48000)) for i in range(48000*4))).tobytes())
                library=await invoke('audio_library_import',paths=[str(clip_path)],copy=True,recursive=False)
                clip_id=next(e['id'] for e in library['entries'] if e['name']=='clip')
                await command('refresh')
                baseline=nonzero
                await command('play',id=clip_id)
                await asyncio.sleep(.4)
                assert nonzero>baseline, 'No clip PCM received'
                await command('clip',id=clip_id,action='pause',value=True)
                await command('clip',id=clip_id,action='gain',value=.5)
                await command('clip',id=clip_id,action='loop',value=True)
                seek=await command('clip',id=clip_id,action='seek',value=48000)
                track=next(t for t in seek['tracks'] if t['id']==clip_id)
                assert track['paused'] and track['loop'] and track['gain']==.5 and track['pos']==48000,track
                await command('clip',id=clip_id,action='pause',value=False)
                await asyncio.sleep(.4)
                await command('clip',action='stop_all')
                assert not (await command('ping'))['tracks']
                print('CLIP_PLAY_PAUSE_SEEK_LOOP_GAIN_STOP_OK',flush=True)
            await command('phone_status', microphone_ready=True, monitor=False)
            status = await invoke('mobile_status')
            assert status['connected'] and status['device']['phone']['microphone_ready']
            assert not status['pc_monitor']['enabled'] and not status['voice_output']['enabled']
            await invoke('mobile_action', action={'type': 'computer'})
            await command('phone_status', microphone_ready=True)
            assert not (await invoke('mobile_status'))['selected'], 'Heartbeat stole desktop input'
            await invoke('mobile_action', action={'type': 'use'})
            await command('select', voice=welcome['voices'][0]['id'], profile='__default__')
            await command('settings', patch={'pitch': 0, 'out_gain_db': 0, 'index_rate': 0.0, 'I_noise_reduce': True})
            async def capture():
                index = 0
                deadline = time.monotonic()
                while True:
                    if latest.get('running'):
                        frame = array.array('h', (int(5000 * (0.5 + 0.5 * math.sin((index + j) / 48000 * math.pi * 3)) *
                            (math.sin(2 * math.pi * 180 * (index + j) / 48000) + 0.3 * math.sin(2 * math.pi * 360 * (index + j) / 48000))) for j in range(960)))
                        await ws.send_bytes(frame.tobytes())
                        index += 960
                    deadline += .02
                    await asyncio.sleep(max(0, deadline - time.monotonic()))
            sender = asyncio.create_task(capture())
            async def heartbeat():
                while True:
                    await command('phone_status', microphone_ready=True, monitor=False)
                    await asyncio.sleep(1)
            heart = asyncio.create_task(heartbeat())
            try:
                started = await command('start')
                assert started['running'], started
                print('REAL_ENGINE_RUNNING', flush=True)
                for _ in range(max(1, args.seconds // 10)):
                    await asyncio.sleep(10)
                    print(json.dumps({'frames': frames, 'nonzero': nonzero, 'proc_ms': latest.get('proc_ms'), 'drops': latest.get('drops'), 'running': latest.get('running'), 'engine_error': latest.get('engine_error')}), flush=True)
                    assert latest.get('running'), latest
                heart.cancel();await asyncio.gather(heart,return_exceptions=True)
                await command('phone_status',microphone_ready=False,monitor=False)
                await asyncio.sleep(.5)
                assert not latest.get('running')
                assert nonzero > 0 and any(v > 0 for v in proc), 'No measured inference output'
                assert (await invoke('mobile_status'))['connected']
                report = {'frames': frames, 'nonzero_frames': nonzero, 'peak': max(peaks, default=0),
                          'processing_ms_max': max(proc, default=0), 'drops': latest.get('drops'), 'seconds': args.seconds}
                out.joinpath('audio-report.json').write_text(json.dumps(report, indent=2))
                print(json.dumps(report), flush=True)
            finally:
                sender.cancel(); heart.cancel()
                await asyncio.gather(sender, heart, return_exceptions=True)
                await invoke('mobile_action', action={'type': 'stop'})
                reader.cancel(); await asyncio.gather(reader, return_exceptions=True)
        await asyncio.sleep(.3)
        async with session.ws_connect(endpoint + '/v1/ws', headers=headers) as ws:
            assert (await ws.receive_json())['type'] == 'welcome'
        await invoke('mobile_action', action={'type': 'revoke', 'id': 'integration-test'})
        async with session.get(endpoint + '/v1/health', headers=headers) as response:
            assert response.status == 401
        print('PAIRING_RECONNECT_REVOKE_OK', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--host')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--invite-only', action='store_true')
    parser.add_argument('--show', action='store_true')
    parser.add_argument('--quit', action='store_true')
    parser.add_argument('--media-only', action='store_true')
    parser.add_argument('--clips', action='store_true')
    asyncio.run(main(parser.parse_args()))
