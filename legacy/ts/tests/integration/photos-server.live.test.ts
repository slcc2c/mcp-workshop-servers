import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { PhotosServer } from '../../servers/photos/index.js';

const runLive = process.env.PHOTOS_LIVE_TESTS === '1';

describe.skipIf(!runLive)('PhotosServer live integration', () => {
  const server = new PhotosServer();

  beforeAll(async () => {
    await server.initialize();
  });

  afterAll(async () => {
    await server.shutdown();
  });

  it('lists albums from the local Photos library', async () => {
    const result = await server.executeTool('photos_list_albums', {
      includeSmart: true,
      limit: 5,
      offset: 0,
    });

    expect(result).toMatchObject({
      total: expect.any(Number),
      albums: expect.any(Array),
    });
  });

  it('searches assets and can read one asset by id when available', async () => {
    const searchResult = await server.executeTool('photos_search_assets', {
      limit: 1,
      offset: 0,
      sort: 'created_desc',
      mediaType: 'any',
    });

    expect(searchResult).toMatchObject({
      total: expect.any(Number),
      items: expect.any(Array),
    });

    const typedSearch = searchResult as {
      total: number;
      items: Array<{ id: string; filename: string }>;
    };

    if (typedSearch.total < 1 || typedSearch.items.length < 1) {
      return;
    }

    const first = typedSearch.items[0];
    const assetResult = await server.executeTool('photos_get_asset', {
      assetId: first.id,
    });

    expect(assetResult).toMatchObject({
      item: {
        id: first.id,
        filename: first.filename,
      },
    });
  });
});
