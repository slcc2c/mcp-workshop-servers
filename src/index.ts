/**
 * Main entry point for MCP Workshop Servers
 */

import { MCPGateway } from './gateway/index.js';
import { loadServerConfig, ensureDirectories } from './utils/config';
import { logger } from './utils/logger';
// import { ServerConfig } from './types/config';

async function main() {
  try {
    logger.info('Starting MCP Workshop Servers...');
    
    // Ensure required directories exist
    await ensureDirectories();
    
    // Load configuration
    const configPath = process.env.CONFIG_PATH;
    const config = await loadServerConfig(configPath);
    
    // Create and start gateway
    const gateway = new MCPGateway(config);
    
    // Handle shutdown gracefully
    const shutdown = async (signal: string) => {
      logger.info(`Received ${signal}, shutting down gracefully...`);
      try {
        await gateway.stop();
        process.exit(0);
      } catch (error) {
        logger.error('Error during shutdown', { error });
        process.exit(1);
      }
    };
    
    process.on('SIGTERM', () => shutdown('SIGTERM'));
    process.on('SIGINT', () => shutdown('SIGINT'));
    
    // Start the gateway
    await gateway.start();
    
    logger.info('MCP Workshop Servers started successfully!');
    logger.info('Access the gateway at http://localhost:' + config.gateway.port);
  } catch (error) {
    logger.error('Failed to start MCP Workshop Servers', { error });
    process.exit(1);
  }
}

// Run if this is the main module
if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}

export { MCPGateway } from './gateway/index.js';
export * from './types';
export * from './utils/logger';
export * from './utils/config';
export * from './utils/errors';