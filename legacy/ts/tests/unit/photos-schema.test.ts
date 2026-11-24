import { afterEach, describe, expect, it } from 'vitest';
import { InvalidParamsError } from '../../src/utils/errors.js';
import { PhotosServer } from '../../servers/photos/index.js';
import { PhotosOperation, PhotosScriptRunner } from '../../servers/photos/photos-osascript.js';

class StaticRunner implements PhotosScriptRunner {
  constructor(
    private readonly payloadByOperation: Partial<
      Record<PhotosOperation, Record<string, unknown>>
    >
  ) {}

  async runOperation(
    operation: PhotosOperation,
    _args: Record<string, unknown>
  ): Promise<unknown> {
    const payload = this.payloadByOperation[operation];
    if (!payload) {
      throw new Error(`No payload for operation ${operation}`);
    }
    return payload;
  }
}

describe('PhotosServer schema validation', () => {
  const previousExportRoot = process.env.PHOTOS_EXPORT_ROOT;

  afterEach(() => {
    if (previousExportRoot === undefined) {
      delete process.env.PHOTOS_EXPORT_ROOT;
    } else {
      process.env.PHOTOS_EXPORT_ROOT = previousExportRoot;
    }
  });

  it('rejects invalid date filters via input schema', async () => {
    const server = new PhotosServer(
      new StaticRunner({
        search_assets: { total: 0, items: [] },
      })
    );
    await server.initialize();

    await expect(
      server.executeTool('photos_search_assets', {
        dateFrom: 'not-a-date',
      })
    ).rejects.toBeInstanceOf(InvalidParamsError);

    await server.shutdown();
  });

  it('rejects out-of-range search limits via input schema', async () => {
    const server = new PhotosServer(
      new StaticRunner({
        search_assets: { total: 0, items: [] },
      })
    );
    await server.initialize();

    await expect(
      server.executeTool('photos_search_assets', {
        limit: 900,
      })
    ).rejects.toBeInstanceOf(InvalidParamsError);

    await server.shutdown();
  });

  it('accepts rich metadata payloads', async () => {
    const server = new PhotosServer(
      new StaticRunner({
        search_assets: {
          total: 1,
          items: [
            {
              id: 'asset-1',
              filename: 'IMG_1234.JPG',
              mediaType: 'image',
              createdAt: '2026-03-01T10:00:00.000Z',
              modifiedAt: '2026-03-01T11:00:00.000Z',
              width: 4000,
              height: 3000,
              durationSeconds: null,
              favorite: false,
              hidden: false,
              albumIds: ['album-1'],
              albumNames: ['Camera Roll'],
              keywords: ['test'],
              location: { latitude: 1.23, longitude: 4.56 },
              isCloudShared: true,
            },
          ],
        },
      })
    );
    await server.initialize();

    const result = await server.executeTool('photos_search_assets', {});
    expect(result).toMatchObject({
      total: 1,
      items: [{ id: 'asset-1', filename: 'IMG_1234.JPG' }],
    });

    await server.shutdown();
  });

  it('rejects malformed script payloads', async () => {
    const server = new PhotosServer(
      new StaticRunner({
        get_asset: {
          item: {
            id: 'asset-1',
          },
        },
      })
    );
    await server.initialize();

    await expect(
      server.executeTool('photos_get_asset', {
        assetId: 'asset-1',
      })
    ).rejects.toMatchObject({
      data: { photosCode: 'PHOTOS_SCRIPT_ERROR' },
    });

    await server.shutdown();
  });
});

