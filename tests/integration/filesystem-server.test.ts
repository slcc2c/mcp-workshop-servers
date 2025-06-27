/**
 * Integration tests for Filesystem Server
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { FilesystemServer } from '../../servers/filesystem';
import { promises as fs } from 'fs';
import path from 'path';
import os from 'os';

describe('FilesystemServer Integration', () => {
  let server: FilesystemServer;
  let testDir: string;

  beforeEach(async () => {
    // Create a temporary directory for testing
    testDir = await fs.mkdtemp(path.join(os.tmpdir(), 'mcp-fs-test-'));
    
    // Set up server with test directory as allowed path
    server = new FilesystemServer();
    (server as any).allowedPaths = [testDir];
    
    await server.initialize();
  });

  afterEach(async () => {
    await server.shutdown();
    
    // Clean up test directory
    try {
      await fs.rm(testDir, { recursive: true, force: true });
    } catch (error) {
      // Ignore cleanup errors
    }
  });

  describe('File Operations', () => {
    it('should write and read files', async () => {
      const testFile = 'test.txt';
      const testContent = 'Hello, World!';

      // Write file
      const writeResult = await server.executeTool('fs_write_file', {
        path: testFile,
        content: testContent,
        encoding: 'utf8'
      });

      expect(writeResult).toMatchObject({
        path: testFile,
        size: expect.any(Number)
      });

      // Read file
      const readResult = await server.executeTool('fs_read_file', {
        path: testFile,
        encoding: 'utf8'
      });

      expect(readResult).toMatchObject({
        path: testFile,
        content: testContent,
        size: testContent.length,
        encoding: 'utf8'
      });
    });

    it('should handle binary files', async () => {
      const testFile = 'binary.dat';
      const binaryData = Buffer.from([0x48, 0x65, 0x6c, 0x6c, 0x6f]).toString('base64');

      // Write binary file
      await server.executeTool('fs_write_file', {
        path: testFile,
        content: binaryData,
        encoding: 'base64'
      });

      // Read binary file
      const readResult = await server.executeTool('fs_read_file', {
        path: testFile,
        encoding: 'base64'
      });

      expect(readResult).toMatchObject({
        content: binaryData,
        encoding: 'base64'
      });
    });

    it('should read file with offset and length', async () => {
      const testFile = 'partial.txt';
      const testContent = 'This is a long test content for partial reading';

      await server.executeTool('fs_write_file', {
        path: testFile,
        content: testContent
      });

      // Read partial content
      const readResult = await server.executeTool('fs_read_file', {
        path: testFile,
        offset: 5,
        length: 10
      });

      expect(readResult).toMatchObject({
        content: 'is a long ',
        size: 10
      });
    });

    it('should copy files', async () => {
      const sourceFile = 'source.txt';
      const destFile = 'destination.txt';
      const content = 'Content to copy';

      // Create source file
      await server.executeTool('fs_write_file', {
        path: sourceFile,
        content
      });

      // Copy file
      const copyResult = await server.executeTool('fs_copy_file', {
        source: sourceFile,
        destination: destFile
      });

      expect(copyResult).toMatchObject({
        source: sourceFile,
        destination: destFile,
        copied: true
      });

      // Verify destination exists and has same content
      const readResult = await server.executeTool('fs_read_file', {
        path: destFile
      });

      expect((readResult as any).content).toBe(content);
    });

    it('should move files', async () => {
      const sourceFile = 'moveme.txt';
      const destFile = 'moved.txt';
      const content = 'Content to move';

      // Create source file
      await server.executeTool('fs_write_file', {
        path: sourceFile,
        content
      });

      // Move file
      const moveResult = await server.executeTool('fs_move_file', {
        source: sourceFile,
        destination: destFile
      });

      expect(moveResult).toMatchObject({
        source: sourceFile,
        destination: destFile,
        moved: true
      });

      // Verify source no longer exists
      const existsResult = await server.executeTool('fs_exists', {
        path: sourceFile
      });

      expect((existsResult as any).exists).toBe(false);

      // Verify destination exists
      const readResult = await server.executeTool('fs_read_file', {
        path: destFile
      });

      expect((readResult as any).content).toBe(content);
    });

    it('should delete files', async () => {
      const testFile = 'delete-me.txt';

      // Create file
      await server.executeTool('fs_write_file', {
        path: testFile,
        content: 'Delete this'
      });

      // Delete file
      const deleteResult = await server.executeTool('fs_delete_file', {
        path: testFile
      });

      expect(deleteResult).toMatchObject({
        path: testFile,
        deleted: true
      });

      // Verify file no longer exists
      const existsResult = await server.executeTool('fs_exists', {
        path: testFile
      });

      expect((existsResult as any).exists).toBe(false);
    });
  });

  describe('Directory Operations', () => {
    it('should create directories', async () => {
      const dirPath = 'test-dir/sub-dir';

      const createResult = await server.executeTool('fs_create_directory', {
        path: dirPath,
        recursive: true
      });

      expect(createResult).toMatchObject({
        path: dirPath,
        created: true
      });

      // Verify directory exists
      const existsResult = await server.executeTool('fs_exists', {
        path: dirPath
      });

      expect((existsResult as any).exists).toBe(true);
    });

    it('should list directory contents', async () => {
      const subDir = 'list-test';
      
      // Create directory and files
      await server.executeTool('fs_create_directory', { path: subDir });
      await server.executeTool('fs_write_file', {
        path: path.join(subDir, 'file1.txt'),
        content: 'File 1'
      });
      await server.executeTool('fs_write_file', {
        path: path.join(subDir, 'file2.txt'),
        content: 'File 2'
      });

      // List directory
      const listResult = await server.executeTool('fs_list_directory', {
        path: subDir,
        details: true
      });

      expect(listResult).toMatchObject({
        path: subDir,
        count: 2,
        items: expect.arrayContaining([
          expect.objectContaining({
            name: 'file1.txt',
            type: 'file',
            size: expect.any(Number)
          }),
          expect.objectContaining({
            name: 'file2.txt',
            type: 'file'
          })
        ])
      });
    });

    it('should list recursively', async () => {
      const baseDir = 'recursive-test';
      const subDir = path.join(baseDir, 'subdir');

      // Create nested structure
      await server.executeTool('fs_create_directory', { path: subDir });
      await server.executeTool('fs_write_file', {
        path: path.join(baseDir, 'root.txt'),
        content: 'Root file'
      });
      await server.executeTool('fs_write_file', {
        path: path.join(subDir, 'nested.txt'),
        content: 'Nested file'
      });

      // List recursively
      const listResult = await server.executeTool('fs_list_directory', {
        path: baseDir,
        recursive: true
      });

      expect((listResult as any).count).toBeGreaterThanOrEqual(3); // root.txt, subdir, nested.txt
      expect((listResult as any).items).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ name: 'root.txt' }),
          expect.objectContaining({ name: 'subdir', type: 'directory' }),
          expect.objectContaining({ name: 'nested.txt' })
        ])
      );
    });

    it('should delete directories', async () => {
      const dirPath = 'delete-dir';
      const filePath = path.join(dirPath, 'file.txt');

      // Create directory with file
      await server.executeTool('fs_create_directory', { path: dirPath });
      await server.executeTool('fs_write_file', {
        path: filePath,
        content: 'File in directory'
      });

      // Delete directory recursively
      const deleteResult = await server.executeTool('fs_delete_directory', {
        path: dirPath,
        recursive: true
      });

      expect(deleteResult).toMatchObject({
        path: dirPath,
        deleted: true,
        recursive: true
      });

      // Verify directory no longer exists
      const existsResult = await server.executeTool('fs_exists', {
        path: dirPath
      });

      expect((existsResult as any).exists).toBe(false);
    });
  });

  describe('File Information', () => {
    it('should get file statistics', async () => {
      const testFile = 'stats-test.txt';
      const content = 'Test content for stats';

      await server.executeTool('fs_write_file', {
        path: testFile,
        content
      });

      const statsResult = await server.executeTool('fs_get_stats', {
        path: testFile
      });

      expect(statsResult).toMatchObject({
        path: testFile,
        type: 'file',
        size: content.length,
        created: expect.any(String),
        modified: expect.any(String),
        isReadable: true,
        isWritable: true
      });
    });

    it('should check file existence', async () => {
      const existingFile = 'exists.txt';
      const nonExistentFile = 'does-not-exist.txt';

      // Create file
      await server.executeTool('fs_write_file', {
        path: existingFile,
        content: 'I exist'
      });

      // Check existing file
      const existsResult = await server.executeTool('fs_exists', {
        path: existingFile
      });

      expect(existsResult).toMatchObject({
        exists: true,
        path: existingFile
      });

      // Check non-existent file
      const notExistsResult = await server.executeTool('fs_exists', {
        path: nonExistentFile
      });

      expect(notExistsResult).toMatchObject({
        exists: false,
        path: nonExistentFile
      });
    });
  });

  describe('Search Operations', () => {
    beforeEach(async () => {
      // Set up test files for searching
      await server.executeTool('fs_create_directory', { path: 'search-test' });
      
      await server.executeTool('fs_write_file', {
        path: 'search-test/javascript.js',
        content: 'console.log("Hello JavaScript");'
      });
      
      await server.executeTool('fs_write_file', {
        path: 'search-test/python.py',
        content: 'print("Hello Python")'
      });
      
      await server.executeTool('fs_write_file', {
        path: 'search-test/readme.txt',
        content: 'This is a README file with JavaScript mention'
      });
    });

    it('should search file contents', async () => {
      const searchResult = await server.executeTool('fs_search_files', {
        path: 'search-test',
        query: 'JavaScript',
        searchContent: true,
        searchNames: false
      });

      expect((searchResult as any).count).toBeGreaterThanOrEqual(2);
      expect((searchResult as any).results).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ name: 'javascript.js' }),
          expect.objectContaining({ name: 'readme.txt' })
        ])
      );
    });

    it('should search file names', async () => {
      const searchResult = await server.executeTool('fs_search_files', {
        path: 'search-test',
        query: 'python',
        searchContent: false,
        searchNames: true,
        caseSensitive: false
      });

      expect((searchResult as any).count).toBe(1);
      expect((searchResult as any).results[0]).toMatchObject({
        name: 'python.py'
      });
    });

    it('should respect file patterns', async () => {
      const searchResult = await server.executeTool('fs_search_files', {
        path: 'search-test',
        query: '',
        filePattern: '*.js',
        searchContent: false,
        searchNames: true
      });

      expect((searchResult as any).count).toBe(1);
      expect((searchResult as any).results[0]).toMatchObject({
        name: 'javascript.js'
      });
    });
  });

  describe('File Watching', () => {
    it('should create and manage watchers', async () => {
      const watchDir = 'watch-test';
      await server.executeTool('fs_create_directory', { path: watchDir });

      // Create watcher
      const watchResult = await server.executeTool('fs_watch_path', {
        path: watchDir,
        events: ['add', 'change'],
        recursive: true
      });

      expect(watchResult).toMatchObject({
        watcherId: expect.stringMatching(/^watcher-/),
        path: watchDir,
        events: ['add', 'change'],
        recursive: true
      });

      const watcherId = (watchResult as any).watcherId;

      // List watchers
      const listResult = await server.executeTool('fs_list_watchers', {});
      expect((listResult as any).count).toBe(1);
      expect((listResult as any).watchers[0]).toMatchObject({
        id: watcherId,
        path: watchDir
      });

      // Stop watcher
      const unwatchResult = await server.executeTool('fs_unwatch_path', {
        watcherId
      });

      expect(unwatchResult).toMatchObject({
        watcherId,
        stopped: true
      });

      // Verify watcher is removed
      const listAfterResult = await server.executeTool('fs_list_watchers', {});
      expect((listAfterResult as any).count).toBe(0);
    });
  });

  describe('Security and Validation', () => {
    it('should prevent path traversal attacks', async () => {
      await expect(
        server.executeTool('fs_read_file', {
          path: '../../../etc/passwd'
        })
      ).rejects.toThrow('Permission denied');
    });

    it('should prevent access to blocked directories', async () => {
      await expect(
        server.executeTool('fs_read_file', {
          path: '/etc/passwd'
        })
      ).rejects.toThrow('Permission denied');
    });

    it('should enforce file size limits', async () => {
      const largeContent = 'x'.repeat(20 * 1024 * 1024); // 20MB

      await expect(
        server.executeTool('fs_write_file', {
          path: 'large-file.txt',
          content: largeContent
        })
      ).rejects.toThrow('Content too large');
    });

    it('should handle non-existent files gracefully', async () => {
      await expect(
        server.executeTool('fs_read_file', {
          path: 'non-existent.txt'
        })
      ).rejects.toThrow('Resource \'non-existent.txt\' not found');
    });
  });

  describe('Operation Tracking', () => {
    it('should track file operations when enabled', async () => {
      // Check tracking status
      const statusResult = await server.executeTool('getRecentOperations', {});
      expect((statusResult as any).trackingEnabled).toBe(true);

      // Perform a file operation
      await server.executeTool('fs_write_file', {
        path: 'tracked-file.txt',
        content: 'This operation should be tracked'
      });

      // The operation tracking is logged (in a real implementation, 
      // this would be stored in the Memory server)
    });

    it('should toggle operation tracking', async () => {
      // Disable tracking
      const disableResult = await server.executeTool('toggleOperationTracking', {
        enabled: false
      });

      expect(disableResult).toMatchObject({
        trackingEnabled: false,
        changed: true
      });

      // Enable tracking
      const enableResult = await server.executeTool('toggleOperationTracking', {
        enabled: true
      });

      expect(enableResult).toMatchObject({
        trackingEnabled: true,
        changed: true
      });
    });
  });

  describe('Working Directory', () => {
    it('should return working directory information', async () => {
      const cwdResult = await server.executeTool('fs_get_working_directory', {});

      expect(cwdResult).toMatchObject({
        cwd: expect.any(String),
        allowed: expect.arrayContaining([testDir])
      });
    });
  });
});