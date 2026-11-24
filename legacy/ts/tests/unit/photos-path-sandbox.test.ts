import { promises as fs } from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MCPErrorCode } from '../../src/types/mcp.js';
import { PhotosServer } from '../../servers/photos/index.js';
import { PhotosOperation, PhotosScriptRunner } from '../../servers/photos/photos-osascript.js';

class ExportCaptureRunner implements PhotosScriptRunner {
  public operation: PhotosOperation | null = null;
  public args: Record<string, unknown> | null = null;

  async runOperation(
    operation: PhotosOperation,
    args: Record<string, unknown>
  ): Promise<unknown> {
    this.operation = operation;
    this.args = args;

    return {
      destinationPath: String(args.destinationPath ?? ''),
      exported: [],
      failed: [],
    };
  }
}

describe('PhotosServer export path sandbox', () => {
  let previousExportRoot: string | undefined;
  let tempRoot: string;

  beforeEach(async () => {
    previousExportRoot = process.env.PHOTOS_EXPORT_ROOT;
    tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'photos-export-root-'));
  });

  afterEach(async () => {
    if (previousExportRoot === undefined) {
      delete process.env.PHOTOS_EXPORT_ROOT;
    } else {
      process.env.PHOTOS_EXPORT_ROOT = previousExportRoot;
    }
    await fs.rm(tempRoot, { recursive: true, force: true });
  });

  it('requires PHOTOS_EXPORT_ROOT for export', async () => {
    delete process.env.PHOTOS_EXPORT_ROOT;
    const server = new PhotosServer(new ExportCaptureRunner());
    await server.initialize();

    await expect(
      server.executeTool('photos_export_assets', {
        assetIds: ['asset-1'],
      })
    ).rejects.toMatchObject({
      code: MCPErrorCode.PermissionDenied,
      data: { photosCode: 'PHOTOS_EXPORT_ROOT_REQUIRED' },
    });

    await server.shutdown();
  });

  it('rejects traversal with destinationSubdir', async () => {
    process.env.PHOTOS_EXPORT_ROOT = tempRoot;
    const server = new PhotosServer(new ExportCaptureRunner());
    await server.initialize();

    await expect(
      server.executeTool('photos_export_assets', {
        assetIds: ['asset-1'],
        destinationSubdir: '../outside',
      })
    ).rejects.toMatchObject({
      code: MCPErrorCode.PermissionDenied,
      data: { photosCode: 'PHOTOS_EXPORT_PATH_DENIED' },
    });

    await server.shutdown();
  });

  it('rejects symlink escape paths', async () => {
    process.env.PHOTOS_EXPORT_ROOT = tempRoot;
    const outside = await fs.mkdtemp(path.join(os.tmpdir(), 'photos-outside-'));
    await fs.symlink(outside, path.join(tempRoot, 'escape-link'));
    const leakedNestedDir = path.join(outside, 'nested');

    const server = new PhotosServer(new ExportCaptureRunner());
    await server.initialize();

    await expect(
      server.executeTool('photos_export_assets', {
        assetIds: ['asset-1'],
        destinationSubdir: 'escape-link/nested',
      })
    ).rejects.toMatchObject({
      code: MCPErrorCode.PermissionDenied,
      data: { photosCode: 'PHOTOS_EXPORT_PATH_DENIED' },
    });

    // Rejecting path escape must not create directories outside export root.
    await expect(fs.access(leakedNestedDir)).rejects.toBeTruthy();

    await server.shutdown();
    await fs.rm(outside, { recursive: true, force: true });
  });

  it('resolves valid paths within export root', async () => {
    process.env.PHOTOS_EXPORT_ROOT = tempRoot;
    const runner = new ExportCaptureRunner();
    const server = new PhotosServer(runner);
    await server.initialize();

    const result = await server.executeTool('photos_export_assets', {
      assetIds: ['asset-1'],
      destinationSubdir: 'safe/session',
    });

    const realRoot = await fs.realpath(tempRoot);
    const expectedDestination = path.join(realRoot, 'safe/session');

    expect(runner.operation).toBe('export_assets');
    expect(runner.args?.destinationPath).toBe(expectedDestination);
    expect(result).toMatchObject({
      destinationRoot: realRoot,
      destinationPath: expectedDestination,
      exported: [],
      failed: [],
    });

    await server.shutdown();
  });
});
