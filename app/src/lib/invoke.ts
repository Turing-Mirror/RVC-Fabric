import { invoke as nativeInvoke, type InvokeArgs, type InvokeOptions } from "@tauri-apps/api/core";
import { commandFeature, DiagnosticError, diagnosticPayload, type Feature } from "./diagnostics";

/** Explicit feature attribution when a command prefix does not match the user's current task. */
export async function invokeFor<T>(feature: Feature, command: string, ...rest: [args?: InvokeArgs, options?: InvokeOptions]): Promise<T> {
  try { return diagnosticPayload(await nativeInvoke<T>(command, ...rest)); }
  catch (error) { throw new DiagnosticError(error, feature, true); }
}

/** Unknown IPC failures stay local: never recursively invoke a failed bridge to diagnose it. */
export async function invoke<T>(command: string, ...rest: [args?: InvokeArgs, options?: InvokeOptions]): Promise<T> {
  try { return diagnosticPayload(await nativeInvoke<T>(command, ...rest)); }
  catch (error) { throw new DiagnosticError(error, commandFeature(command)); }
}
