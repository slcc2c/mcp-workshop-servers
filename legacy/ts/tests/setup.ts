/**
 * Test setup file
 */

import { beforeAll, afterAll } from 'vitest';
import { config } from 'dotenv';

// Load test environment variables
config({ path: '.env.test' });

beforeAll(async () => {
  // Global test setup
  console.log('🧪 Setting up test environment');
});

afterAll(async () => {
  // Global test cleanup
  console.log('🧹 Cleaning up test environment');

