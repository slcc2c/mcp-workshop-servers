import { promises as fs } from 'fs';
import os from 'os';
import path from 'path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { MCPErrorCode } from '../../src/types/mcp.js';
import { PhotosServer } from '../../servers/photos/index.js';
import {
  PhotosOperation,
  PhotosScriptError,
  PhotosScriptRunner,
} from '../../servers/photos/photos-osascript.js';

interface RunnerCall {
  operation: PhotosOperation;
  args: Record<string, unknown>;
}

class MockRunner implements PhotosScriptRunner {
  public readonly calls: RunnerCall[] = [];

  constructor(
    private readonly handlers: Partial<
      Record<PhotosOperation, (args: Record<string, unknown>) => unknown>
    >
  ) {}

  async runOperation(
    operation: PhotosOperation,
    args: Record<string, unknown>
  ): Promise<unknown> {
    this.calls.push({ operation, args });

    const handler = this.handlers[operation];
    if (!handler) {
      throw new Error(`No mock handler for operation: ${operation}`);
    }

    return handler(args);
  }
}

describe('PhotosServer integration (mocked osascript)', () => {
  let tempRoot: string;
  let previousExportRoot: string | undefined;

  beforeEach(async () => {
    previousExportRoot = process.env.PHOTOS_EXPORT_ROOT;
    tempRoot = await fs.mkdtemp(path.join(os.tmpdir(), 'photos-mcp-test-'));
    process.env.PHOTOS_EXPORT_ROOT = tempRoot;
  });

  afterEach(async () => {
    if (previousExportRoot === undefined) {
      delete process.env.PHOTOS_EXPORT_ROOT;
    } else {
      process.env.PHOTOS_EXPORT_ROOT = previousExportRoot;
    }

    await fs.rm(tempRoot, { recursive: true, force: true });
  });

  it('lists albums from the runner', async () => {
    const runner = new MockRunner({
      list_albums: () => ({
        total: 2,
        albums: [
          { id: 'a1', name: 'Trips', isSmart: false, assetCount: 42 },
          { id: 'a2', name: 'Favorites', isSmart: true, assetCount: 12 },
        ],
      }),
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    const result = await server.executeTool('photos_list_albums', {
      includeSmart: true,
      limit: 50,
      offset: 0,
    });

    expect(result).toMatchObject({
      total: 2,
      albums: [
        { id: 'a1', name: 'Trips', isSmart: false, assetCount: 42 },
        { id: 'a2', name: 'Favorites', isSmart: true, assetCount: 12 },
      ],
    });
    expect(runner.calls).toHaveLength(1);
    expect(runner.calls[0]?.operation).toBe('list_albums');

    await server.shutdown();
  });

  it('searches assets with rich metadata', async () => {
    const runner = new MockRunner({
      search_assets: () => ({
        total: 1,
        items: [
          {
            id: 'asset-1',
            filename: 'IMG_0001.JPG',
            mediaType: 'image',
            createdAt: '2026-02-20T10:00:00.000Z',
            modifiedAt: '2026-02-21T10:00:00.000Z',
            width: 4032,
            height: 3024,
            durationSeconds: null,
            favorite: true,
            hidden: false,
            albumIds: ['a1'],
            albumNames: ['Trips'],
            keywords: ['vacation'],
            location: { latitude: 41.8781, longitude: -87.6298 },
            isCloudShared: false,
          },
        ],
      }),
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    const result = await server.executeTool('photos_search_assets', {
      query: 'img',
      mediaType: 'image',
      sort: 'created_desc',
      limit: 10,
      offset: 0,
    });

    expect(result).toMatchObject({
      total: 1,
      items: [
        {
          id: 'asset-1',
          filename: 'IMG_0001.JPG',
          favorite: true,
          albumNames: ['Trips'],
        },
      ],
    });

    await server.shutdown();
  });

  it('gets one asset by id', async () => {
    const runner = new MockRunner({
      get_asset: (args) => ({
        item: {
          id: String(args.assetId),
          filename: 'IMG_0009.JPG',
          mediaType: 'image',
          createdAt: '2026-02-20T10:00:00.000Z',
          modifiedAt: null,
          width: 3000,
          height: 2000,
          durationSeconds: null,
          favorite: false,
          hidden: false,
          albumIds: [],
          albumNames: [],
          keywords: [],
          location: null,
          isCloudShared: false,
        },
      }),
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    const result = await server.executeTool('photos_get_asset', {
      assetId: 'asset-9',
    });

    expect(result).toMatchObject({
      item: { id: 'asset-9', filename: 'IMG_0009.JPG' },
    });

    await server.shutdown();
  });

  it('exports assets into the sandboxed root', async () => {
    const runner = new MockRunner({
      export_assets: (args) => ({
        destinationPath: String(args.destinationPath),
        exported: [
          {
            assetId: 'asset-1',
            filePath: path.join(String(args.destinationPath), 'IMG_0001.JPG'),
          },
        ],
        failed: [],
      }),
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    const result = await server.executeTool('photos_export_assets', {
      assetIds: ['asset-1'],
      destinationSubdir: 'exports/session-1',
      overwrite: false,
      exportVariant: 'current',
    });

    const realRoot = await fs.realpath(tempRoot);
    const expectedDestination = path.join(realRoot, 'exports/session-1');

    expect(result).toMatchObject({
      destinationRoot: realRoot,
      destinationPath: expectedDestination,
      exported: [{ assetId: 'asset-1' }],
      failed: [],
    });
    expect(runner.calls).toHaveLength(1);
    expect(runner.calls[0]?.operation).toBe('export_assets');
    expect(runner.calls[0]?.args.destinationPath).toBe(expectedDestination);

    await server.shutdown();
  });

  it('maps PhotosScriptError codes to MCP error codes', async () => {
    const runner = new MockRunner({
      search_assets: () => {
        throw new PhotosScriptError(
          'PHOTOS_AUTOMATION_DENIED',
          'Apple Events permission denied'
        );
      },
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    await expect(
      server.executeTool('photos_search_assets', {})
    ).rejects.toMatchObject({
      code: MCPErrorCode.PermissionDenied,
      data: { photosCode: 'PHOTOS_AUTOMATION_DENIED' },
    });

    await server.shutdown();
  });

  it('maps PHOTOS_APP_UNAVAILABLE to a resource-not-found style MCP error', async () => {
    const runner = new MockRunner({
      search_assets: () => {
        throw new PhotosScriptError(
          'PHOTOS_APP_UNAVAILABLE',
          "Application can't be found."
        );
      },
    });

    const server = new PhotosServer(runner);
    await server.initialize();

    await expect(
      server.executeTool('photos_search_assets', {})
    ).rejects.toMatchObject({
      code: MCPErrorCode.ResourceNotFound,
      data: { photosCode: 'PHOTOS_APP_UNAVAILABLE' },
    });

    await server.shutdown();
  });
});
