# RVC-Fabric · en-US

| 当前键名 | 原对照表行号 | 应用文本 |
| --- | --- | --- |
| `settings.prewarmTip` | L61 | Automatically loads the current voice model into GPU memory on startup to reduce wait time when starting real-time voice conversion |
| `glossary.terms.hubert.detail` | L62 | Extracts phonetic content features from speech (stripping speaker timbre) and is a required base model for all voice conversion and training tasks. |
| `glossary.terms.directml.detail` | L63 | Windows general-purpose hardware acceleration backend for AMD and integrated GPUs; supports voice conversion inference but does not currently support model training. |
| `glossary.terms.sr.detail` | L64 | Number of audio samples captured per second. During real-time conversion, you can follow either the audio device sample rate or the voice model sample rate; keeping the default is generally recommended. |
| `glossary.terms.wasapi.detail` | L65 | Native Windows audio protocol. Exclusive mode further reduces latency but requires stricter audio hardware compatibility and prevents other applications from using the device simultaneously. |
| `glossary.terms.block.detail` | L66 | Duration of each audio slice sent to the model per inference step. Smaller values reduce latency but increase compute load; setting it too low may cause audio dropouts or distortion. |
| `glossary.terms.crossfade.detail` | L67 | Crossfade duration at the boundary between adjacent audio slices, used to eliminate splicing clicks. Too short may cause clicking; too long may make the audio sound muffled. |
| `glossary.terms.vbcable.detail` | L69 | A virtual audio cable driver: route RVC Fabric's converted output into the virtual audio input, then select the corresponding virtual audio output as your microphone in games or chat apps so others hear your converted voice. |
| `msg.sep.no_request` | L79 | Missing request file parameter |
| `msg.sep.empty_fields` | L80 | Model, input path, and output path cannot be empty |
| `msg.ckpt.info_saved` | L81 | Model metadata saved |
| `msg.ckpt.extracted` | L82 | Inference model extracted |
| `msg.sts.model_is_archive` | L83 | The selected file is a training checkpoint (prefixed with G_ or D_) and cannot be used directly for voice conversion.<br>Turn it into a voice model first via “Advanced → Model extraction” in the training window, then convert. |
| `msg.train.no_slices` | L84 | No sliced audio segments found; please verify that the dataset contains readable audio files |
| `msg.train.oom` | L85 | Insufficient GPU memory. Lower the Batch Size or close other GPU-intensive applications and try again<br>Current batch size: {batch}<br>{log} |
| `msg.train.resume_f0_partial` | L86 | Previous pitch feature extraction completed {done}/{total}; resuming remaining items… |
| `msg.train.resume_feature_partial` | L87 | Previous speech feature extraction completed {done}/{total}; resuming remaining items… |
| `s.0f14377cdd` | L96 | Select your physical microphone device; do not select a virtual audio device |
| `s.1db2e283ac` | L100 | Interface rendering error: {v0} |
| `s.25865a0d91` | L102 | Switching to selected voice… |
| `s.2898cbf891` | L103 | Typically set to your headphones or speakers for local self-monitoring only |
| `s.04c4e3b2b3` | L106 | Download failed: {e} |
| `s.37f36c5824` | L107 | Benchmark completed：{a0} |
| `s.1455f353e7` | L114 | Failed to save file: {e} |
| `s.59f6a509e7` | L115 | Adjusts the output volume gain after conversion to balance final loudness |
| `s.63d89cdb5c` | L118 | Select which GPU to use when multiple NVIDIA GPUs are installed; index order does not reflect GPU performance |
| `s.703e6f531a` | L121 | Verifying and extracting large component archives; exact percentage progress is unavailable during this stage, please wait… |
| `s.7764d6bdd2` | L123 | Background service is not running |
| `s.7dc4ea39fd` | L125 | The training process exited without returning a result; please expand the bottom log panel to investigate |
| `s.9d7d0dbc49` | L127 | Connecting: {a0} |
| `s.bc94a9c280` | L131 | Advanced option; keeping the default value is generally recommended |
| `s.c96a64f150` | L134 | External Audio Interface Routing |
| `s.f5b3cef9e1` | L136 | Dynamic compression engages when audio exceeds this dB level; lower thresholds apply stronger compression |
| `s.f7271a7905` | L137 | The voice conversion process finished without producing an output file; please check the logs |
| `s.f9e62f8c38` | L138 | The benchmark finished without generating a report file |
| `s.ckptModelAHint` | L150 | Primary model (baseline inference model A for merging) |
| `s.ckptAlphaHint` | L151 | Weight ratio for Model A: 1.0 keeps only A, 0.0 keeps only B, and 0.5 blends both equally |
| `s.ckptVersionHint` | L152 | All current standard models use architecture v2; select v1 only for legacy models |
| `s.ckptChangeHint` | L154 | Modifies the metadata embedded inside an inference model file. Click "Inspect" to load existing metadata before editing |
| `s.ckptOnnxOutAuto` | L156 | Leave blank to save in the same directory as the source model (with a .onnx extension) |
| `s.trainSaveWeights` | L157 | Exports an additional ready-to-use inference model at each save interval |
| `s.trainGuideQ6` | L159 | How do I use the model after training? How do I resume if closed midway? |
| `s.dspTipFxTremolo` | L177 | Tremolo: periodically modulates amplitude to create vintage radio or quivering vocal effects |
| `s.dspTipFxChorus` | L178 | Chorus: layers multiple slightly detuned delay voices for a wide, ensemble-like sound |
| `s.dspTipFxBitcrush` | L179 | Bitcrusher: reduces sample rate and bit depth for a lo-fi retro 8-bit texture |
| `s.dspTipFxSweep` | L180 | Triangle pitch sweep: continuously glides pitch back and forth between two semitone bounds |
| `s.dspTipFxPgate` | L181 | Square-wave pitch step: alternates pitch abruptly between two configured semitone steps |
| `s.dspTipFxRectify` | L182 | Half-wave rectification: clips the negative half-cycle of the waveform for a harsh, blown-speaker distortion |
| `s.dspTipFxReverse` | L183 | Reverse grain: plays short live audio slices backward in real time for a reversed-speech effect |
| `s.dspTipFxRevecho` | L184 | Reverse tail reverb: blends reversed decaying speech into the reverb tail for an eerie, haunting ambiance |
| `s.dspTipPRate` | L185 | Modulation or sweep speed |
| `s.dspTipPDepth` | L186 | Modulation depth intensity |
| `s.dspTipPVoices` | L187 | Number of layered chorus voices (more voices create a fuller ensemble) |
| `s.dspTipPTimeMs` | L188 | Echo delay time (milliseconds) |
| `s.dspTipPLo` | L190 | Lower semitone bound for pitch sweep |
| `s.dspTipPHi` | L190 | Upper semitone bound for pitch sweep |
| `s.micTestSilent` | L213 | No audio input signal detected. Please check your microphone connection, system mute settings, or try selecting another input device |
| `s.extraRemoveBusy` | L214 | This component is currently downloading; please wait for the download to finish or cancel it before removing |
| `s.tearAskBlock` | L218 | High audio processing load detected (stuttering or popping may occur). Relax block latency and restart voice conversion automatically? |
| `s.faqDownloadSlowH` | L222 | Resumable downloads are supported; retrying will continue from where the download left off. |
| `s.faqLatencyQ` | L223 | Why is there a noticeable delay between speaking and hearing the converted voice? |
| `s.chkSnapshotModel` | L225 | The selected model file appears to be a training checkpoint (prefixed with G_ or D_) and cannot be used directly for voice conversion<br>{name} |
| `s.errActDownload` | L226 | Go to Downloads |
| `s.errActRuntime` | L226 | Configure Runtime |
| `s.errActExtract` | L226 | Go to Model Extraction |
| `s.errActBatch` | L226 | Adjust Training Parameters |
| `s.trainSrCost` | L227 | Higher sample rates preserve more high-frequency detail but require more GPU memory; choose a lower sample rate when GPU memory is limited. |
| `s.trainStagesIncomplete` | L229 | Incomplete preprocessing steps detected. Continuing training will automatically finish the remaining preprocessing stages first. |
| `s.cleanupDataset` | L231 | Clean up temporary dataset files (sliced segments and feature caches) |
| `s.voiceDeleteFailed` | L232 | Deletion failed. This voice model may currently be in use; please stop real-time conversion or wait for active tasks to finish before retrying.<br>{e} |
| `s.devAutoNoList` | L234 | Please wait for the audio engine to finish starting before running auto-configuration |
| `s.guide.notice.detail` | L237 | When submitting feedback, please describe the exact steps taken, any on-screen messages, and the stage where the issue occurred. |
| `crop.previewBeforeNote` | L241 | Portrait images display only the center section on voice cards; use cropping to adjust the visible area |
