import { execFile, ExecFileOptions } from 'child_process';
import { promisify } from 'util';
import { PHOTOS_JXA_SCRIPT } from './jxa.js';

export type PhotosOperation =
  | 'list_albums'
  | 'search_assets'
  | 'get_asset'
  | 'export_assets';

export interface PhotosScriptRunner {
  runOperation(
    operation: PhotosOperation,
    args: Record<string, unknown>
  ): Promise<unknown>;
}

interface ExecResult {
  stdout: string;
  stderr: string;
}

interface ScriptErrorPayload {
  code?: string;
  message?: string;
  details?: Record<string, unknown>;
}

interface ScriptResponsePayload {
  ok: boolean;
  result?: unknown;
  error?: ScriptErrorPayload;
}

interface ExecErrorLike {
  readonly code?: string | number;
  readonly message?: string;
  readonly stdout?: string | Buffer;
  readonly stderr?: string | Buffer;
  readonly signal?: NodeJS.Signals;
  readonly killed?: boolean;
}

export type OsaScriptExecutor = (
  command: string,
  args: string[],
  options: ExecFileOptions
) => Promise<ExecResult>;

const execFileAsync = promisify(execFile);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function asString(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value instanceof Buffer) {
    return value.toString('utf8');
  }
  if (value === undefined || value === null) {
    return '';
  }
  return String(value);
}

function parseScriptResponse(stdout: string): ScriptResponsePayload {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new PhotosScriptError(
      'PHOTOS_SCRIPT_ERROR',
      'Photos script returned empty output',
      { stdout }
    );
  }

  const lines = trimmed
    .split(/\r?\n/g)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const payloadText = lines.length > 0 ? lines[lines.length - 1] : trimmed;

  let parsed: unknown;
  try {
    parsed = JSON.parse(payloadText);
  } catch (error) {
    throw new PhotosScriptError(
      'PHOTOS_SCRIPT_ERROR',
      'Photos script returned invalid JSON',
      { stdout: payloadText, parseError: asString(error) }
    );
  }

  if (!isRecord(parsed) || typeof parsed.ok !== 'boolean') {
    throw new PhotosScriptError(
      'PHOTOS_SCRIPT_ERROR',
      'Photos script returned unexpected payload',
      { stdout: payloadText }
    );
  }

  return {
    ok: parsed.ok,
    result: parsed.result,
    error: isRecord(parsed.error)
      ? {
          code: typeof parsed.error.code === 'string' ? parsed.error.code : undefined,
          message:
            typeof parsed.error.message === 'string'
              ? parsed.error.message
              : undefined,
          details: isRecord(parsed.error.details)
            ? parsed.error.details
            : undefined,
        }
      : undefined,
  };
}

function inferErrorCode(message: string): string {
  const lowered = message.toLowerCase();
  if (
    lowered.includes('not authorized') ||
    lowered.includes('not permitted') ||
    lowered.includes('apple events')
  ) {
    return 'PHOTOS_AUTOMATION_DENIED';
  }
  if (
    lowered.includes('can’t be found') ||
    lowered.includes("can't be found") ||
    lowered.includes('application isn’t running') ||
    lowered.includes("application isn't running") ||
    lowered.includes('unable to locate application "photos"')
  ) {
    return 'PHOTOS_APP_UNAVAILABLE';
  }
  if (lowered.includes('timeout') || lowered.includes('timed out')) {
    return 'PHOTOS_SCRIPT_TIMEOUT';
  }
  return 'PHOTOS_SCRIPT_ERROR';
}

function defaultExecutor(
  command: string,
  args: string[],
  options: ExecFileOptions
): Promise<ExecResult> {
  return execFileAsync(command, args, options).then((result) => ({
    stdout: asString(result.stdout),
    stderr: asString(result.stderr),
  }));
}

export class PhotosScriptError extends Error {
  constructor(
    public readonly photosCode: string,
    message: string,
    public readonly details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = 'PhotosScriptError';
  }
}

export class OsaScriptPhotosRunner implements PhotosScriptRunner {
  constructor(
    private readonly executor: OsaScriptExecutor = defaultExecutor,
    private readonly timeoutMs: number = 45_000,
    private readonly maxBufferBytes: number = 10 * 1024 * 1024
  ) {}

  async runOperation(
    operation: PhotosOperation,
    args: Record<string, unknown>
  ): Promise<unknown> {
    const encodedArgs = Buffer.from(JSON.stringify(args), 'utf8').toString(
      'base64'
    );

    const env: NodeJS.ProcessEnv = {
      ...process.env,
      MCP_PHOTOS_OPERATION: operation,
      MCP_PHOTOS_ARGS_B64: encodedArgs,
    };

    try {
      const { stdout, stderr } = await this.executor(
        'osascript',
        ['-l', 'JavaScript', '-e', PHOTOS_JXA_SCRIPT],
        {
          env,
          timeout: this.timeoutMs,
          maxBuffer: this.maxBufferBytes,
        }
      );

      const parsed = parseScriptResponse(stdout);
      if (parsed.ok) {
        return parsed.result;
      }

      const errorCode = parsed.error?.code || 'PHOTOS_SCRIPT_ERROR';
      const errorMessage = parsed.error?.message || 'Photos script failed';
      throw new PhotosScriptError(errorCode, errorMessage, {
        ...parsed.error?.details,
        stderr,
      });
    } catch (error) {
      if (error instanceof PhotosScriptError) {
        throw error;
      }

      const execError = (isRecord(error) ? error : {}) as ExecErrorLike;
      const stderr = asString(execError.stderr);
      const stdout = asString(execError.stdout);
      const message =
        asString(execError.message) || stderr || stdout || 'Photos script failed';

      const code = inferErrorCode(message);
      throw new PhotosScriptError(code, message, {
        operation,
        stderr,
        stdout,
        signal: execError.signal ? String(execError.signal) : undefined,
        exitCode:
          execError.code === undefined ? undefined : String(execError.code),
        killed: execError.killed === true,
      });
    }
  }
}
