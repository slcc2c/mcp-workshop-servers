import { describe, expect, it } from 'vitest';
import {
  OsaScriptExecutor,
  OsaScriptPhotosRunner,
  PhotosScriptError,
} from '../../servers/photos/photos-osascript.js';

describe('OsaScriptPhotosRunner', () => {
  it('returns parsed result payloads', async () => {
    const executor: OsaScriptExecutor = async () => ({
      stdout: JSON.stringify({
        ok: true,
        result: { total: 0, items: [] },
      }),
      stderr: '',
    });

    const runner = new OsaScriptPhotosRunner(executor);
    const result = await runner.runOperation('search_assets', {});

    expect(result).toMatchObject({ total: 0, items: [] });
  });

  it('maps script error payloads into PhotosScriptError', async () => {
    const executor: OsaScriptExecutor = async () => ({
      stdout: JSON.stringify({
        ok: false,
        error: {
          code: 'PHOTOS_AUTOMATION_DENIED',
          message: 'Not authorized',
        },
      }),
      stderr: '',
    });

    const runner = new OsaScriptPhotosRunner(executor);

    await expect(runner.runOperation('search_assets', {})).rejects.toMatchObject({
      photosCode: 'PHOTOS_AUTOMATION_DENIED',
      message: 'Not authorized',
    });
  });

  it('maps executor failures into PhotosScriptError', async () => {
    const executor: OsaScriptExecutor = async () => {
      throw Object.assign(new Error('Not authorized to send Apple events'), {
        stderr: 'Not authorized to send Apple events to Photos',
      });
    };

    const runner = new OsaScriptPhotosRunner(executor);
    const operationPromise = runner.runOperation('list_albums', {});

    await expect(operationPromise).rejects.toBeInstanceOf(PhotosScriptError);
    await expect(operationPromise).rejects.toMatchObject({
      photosCode: 'PHOTOS_AUTOMATION_DENIED',
    });
  });
});
