/**
 * Integration tests for Memory Server
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MemoryServer } from '../../servers/memory';
import { promises as fs } from 'fs';
import path from 'path';

describe('MemoryServer Integration', () => {
  let server: MemoryServer;
  const testDataPath = path.join(__dirname, '..', '..', 'tmp', 'test-memory.json');

  beforeEach(async () => {
    server = new MemoryServer();
    // Override data path for testing
    (server as any).dataPath = testDataPath;
    
    await server.initialize();
  });

  afterEach(async () => {
    await server.shutdown();
    
    // Clean up test data
    try {
      await fs.unlink(testDataPath);
    } catch (error) {
      // File might not exist
    }
  });

  it('should store and retrieve memories', async () => {
    // Store a memory
    const storeResult = await server.executeTool('memory_store', {
      content: 'Test memory content',
      type: 'fact',
      tags: ['test', 'integration'],
      metadata: { source: 'test' }
    });

    expect(storeResult).toMatchObject({
      stored: true,
      id: expect.stringMatching(/^mem_/),
    });

    const memoryId = (storeResult as any).id;

    // Retrieve the memory
    const getResult = await server.executeTool('memory_get', {
      id: memoryId
    });

    expect(getResult).toMatchObject({
      id: memoryId,
      content: 'Test memory content',
      type: 'fact',
      tags: ['test', 'integration'],
      metadata: { source: 'test' }
    });
  });

  it('should search memories by content', async () => {
    // Store multiple memories
    await server.executeTool('memory_store', {
      content: 'JavaScript is a programming language',
      type: 'fact',
      tags: ['javascript', 'programming']
    });

    await server.executeTool('memory_store', {
      content: 'Python is also a programming language',
      type: 'fact',
      tags: ['python', 'programming']
    });

    await server.executeTool('memory_store', {
      content: 'I prefer coffee over tea',
      type: 'preference',
      tags: ['personal', 'drinks']
    });

    // Search for programming-related memories
    const searchResult = await server.executeTool('memory_search', {
      query: 'programming',
      limit: 10
    });

    expect(searchResult).toMatchObject({
      query: 'programming',
      totalResults: 2,
      results: expect.arrayContaining([
        expect.objectContaining({
          content: expect.stringContaining('programming'),
          type: 'fact'
        })
      ])
    });
  });

  it('should filter by type and tags', async () => {
    // Store memories of different types
    await server.executeTool('memory_store', {
      content: 'React is a UI library',
      type: 'fact',
      tags: ['react', 'frontend']
    });

    await server.executeTool('memory_store', {
      content: 'I want to learn TypeScript',
      type: 'goal',
      tags: ['typescript', 'learning']
    });

    // Search with type filter
    const factSearch = await server.executeTool('memory_search', {
      query: '',
      type: 'fact',
      limit: 10
    });

    expect(factSearch).toMatchObject({
      totalResults: 1,
      results: expect.arrayContaining([
        expect.objectContaining({
          type: 'fact',
          content: 'React is a UI library'
        })
      ])
    });

    // Search with tag filter
    const tagSearch = await server.executeTool('memory_search', {
      query: '',
      tags: ['frontend'],
      limit: 10
    });

    expect(tagSearch).toMatchObject({
      totalResults: 1,
      results: expect.arrayContaining([
        expect.objectContaining({
          tags: expect.arrayContaining(['frontend'])
        })
      ])
    });
  });

  it('should handle memory relationships', async () => {
    // Store first memory
    const memory1 = await server.executeTool('memory_store', {
      content: 'Node.js is a JavaScript runtime',
      type: 'fact',
      tags: ['nodejs', 'javascript']
    });

    const memory1Id = (memory1 as any).id;

    // Store related memory
    const memory2 = await server.executeTool('memory_store', {
      content: 'Express is a Node.js framework',
      type: 'fact',
      tags: ['express', 'nodejs'],
      relatedTo: [memory1Id]
    });

    const memory2Id = (memory2 as any).id;

    // Get related memories
    const relatedResult = await server.executeTool('memory_get_related', {
      id: memory1Id,
      depth: 1
    });

    expect(relatedResult).toMatchObject({
      id: memory1Id,
      depth: 1,
      relatedEntries: expect.arrayContaining([
        expect.objectContaining({
          id: memory2Id,
          content: 'Express is a Node.js framework'
        })
      ])
    });
  });

  it('should update memories', async () => {
    // Store a memory
    const storeResult = await server.executeTool('memory_store', {
      content: 'Original content',
      type: 'fact',
      tags: ['original']
    });

    const memoryId = (storeResult as any).id;

    // Update the memory
    await server.executeTool('memory_update', {
      id: memoryId,
      content: 'Updated content',
      tags: ['updated', 'modified'],
      metadata: { updated: true }
    });

    // Verify the update
    const getResult = await server.executeTool('memory_get', {
      id: memoryId
    });

    expect(getResult).toMatchObject({
      content: 'Updated content',
      tags: ['updated', 'modified'],
      metadata: { updated: true }
    });
  });

  it('should delete memories', async () => {
    // Store a memory
    const storeResult = await server.executeTool('memory_store', {
      content: 'Memory to delete',
      type: 'fact',
      tags: ['temporary']
    });

    const memoryId = (storeResult as any).id;

    // Delete the memory
    const deleteResult = await server.executeTool('memory_delete', {
      id: memoryId
    });

    expect(deleteResult).toMatchObject({
      id: memoryId,
      deleted: true
    });

    // Verify it's gone
    await expect(
      server.executeTool('memory_get', { id: memoryId })
    ).rejects.toThrow('Memory entry not found');
  });

  it('should list tags', async () => {
    // Store memories with various tags
    await server.executeTool('memory_store', {
      content: 'Test 1',
      type: 'fact',
      tags: ['javascript', 'web']
    });

    await server.executeTool('memory_store', {
      content: 'Test 2',
      type: 'fact',
      tags: ['javascript', 'backend']
    });

    await server.executeTool('memory_store', {
      content: 'Test 3',
      type: 'preference',
      tags: ['personal']
    });

    // List all tags
    const tagsResult = await server.executeTool('memory_list_tags', {});

    expect(tagsResult).toEqual(
      expect.arrayContaining([
        { tag: 'javascript', count: 2 },
        { tag: 'web', count: 1 },
        { tag: 'backend', count: 1 },
        { tag: 'personal', count: 1 }
      ])
    );
  });

  it('should export memory data', async () => {
    // Store some test data
    await server.executeTool('memory_store', {
      content: 'Export test',
      type: 'fact',
      tags: ['export']
    });

    // Export as JSON
    const jsonExport = await server.executeTool('memory_export', {
      format: 'json'
    });

    expect(jsonExport).toMatchObject({
      format: 'json',
      data: {
        entries: expect.arrayContaining([
          expect.objectContaining({
            content: 'Export test',
            type: 'fact'
          })
        ]),
        stats: {
          totalEntries: 1,
          totalTags: 1
        }
      }
    });

    // Export as CSV
    const csvExport = await server.executeTool('memory_export', {
      format: 'csv'
    });

    expect(csvExport).toMatchObject({
      format: 'csv',
      headers: expect.arrayContaining(['id', 'content', 'type', 'timestamp', 'tags']),
      data: expect.arrayContaining([
        expect.objectContaining({
          content: 'Export test',
          type: 'fact'
        })
      ])
    });
  });
});