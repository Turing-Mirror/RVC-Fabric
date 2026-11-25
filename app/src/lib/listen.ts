import { listen as nativeListen, type EventName, type EventCallback, type Options, type UnlistenFn } from "@tauri-apps/api/event";
import { diagnosticPayload } from "./diagnostics";

export function listen<T>(event: EventName, handler: EventCallback<T>, options?: Options): Promise<UnlistenFn> {
  return nativeListen<T>(event, message => handler({ ...message, payload: diagnosticPayload(message.payload) }), options);
}
