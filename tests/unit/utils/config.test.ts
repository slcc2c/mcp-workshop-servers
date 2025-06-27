/**
 * Tests for configuration utilities
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { EnvConfigSchema } from '../../../src/types/config';

describe('Config Utils', () => {
  describe('EnvConfigSchema', () => {
    beforeEach(() => {
      // Reset environment
      delete process.env.NODE_ENV;
      delete process.env.PORT;
      delete process.env.LOG_LEVEL;
    });

    it('should parse valid environment config', () => {
      process.env.NODE_ENV = 'development';
      process.env.PORT = '3000';
      process.env.LOG_LEVEL = 'info';

      const config = EnvConfigSchema.parse(process.env);

      expect(config.NODE_ENV).toBe('development');
      expect(config.PORT).toBe('3000');
      expect(config.LOG_LEVEL).toBe('info');
    });

    it('should use default values', () => {
      const config = EnvConfigSchema.parse({});

      expect(config.NODE_ENV).toBe('development');
      expect(config.PORT).toBe('3000');
      expect(config.LOG_LEVEL).toBe('info');
    });

    it('should validate log level enum', () => {
      process.env.LOG_LEVEL = 'invalid';

      expect(() => EnvConfigSchema.parse(process.env)).toThrow();
    });

    it('should validate node env enum', () => {
      process.env.NODE_ENV = 'invalid';

      expect(() => EnvConfigSchema.parse(process.env)).toThrow();
    });
  });
});