import { Router, Request, Response } from 'express';
import { secureConfig } from '../../utils/secrets-config';
import { createLogger } from '../../utils/logger';

const logger = createLogger('gateway:secrets');
const router = Router();

/**
 * Get available secret providers
 */
router.get('/providers', async (_req: Request, res: Response): Promise<any> => {
  try {
    const secretsManager = secureConfig.getSecretsManager();
    if (!secretsManager) {
      return res.status(503).json({
        error: 'Secrets manager not initialized'
      });
    }

    const providers = secretsManager.getAvailableProviders();
    const providerStatus: Record<string, boolean> = {};
    
    for (const provider of providers) {
      providerStatus[provider] = await secretsManager.isProviderAvailable(provider);
    }

    res.json({
      providers,
      providerStatus,
      defaultProvider: 'ENVIRONMENT' // From config
    });
  } catch (error) {
    logger.error('Failed to get providers', { error });
    res.status(500).json({
      error: 'Failed to get secret providers'
    });
  }
});

/**
 * Get a secret value
 */
router.post('/get', async (req: Request, res: Response): Promise<any> => {
  try {
    const { reference } = req.body;
    
    if (!reference) {
      return res.status(400).json({
        error: 'Secret reference required'
      });
    }

    const value = await secureConfig.get(reference);
    
    res.json({
      value,
      reference,
      cached: true // Simplified - would need to track this
    });
  } catch (error) {
    logger.error('Failed to get secret', { error, reference: req.body.reference });
    res.status(404).json({
      error: error instanceof Error ? error.message : 'Secret not found'
    });
  }
});

/**
 * List available secrets
 */
router.get('/list', async (req: Request, res: Response): Promise<any> => {
  try {
    const secretsManager = secureConfig.getSecretsManager();
    if (!secretsManager) {
      return res.status(503).json({
        error: 'Secrets manager not initialized'
      });
    }

    const provider = req.query.provider as string | undefined;
    const prefix = req.query.prefix as string | undefined;
    
    const secrets = await secretsManager.listSecrets(provider as any, prefix);
    
    res.json({
      secrets,
      count: secrets.length,
      provider: provider || 'all'
    });
  } catch (error) {
    logger.error('Failed to list secrets', { error });
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Failed to list secrets'
    });
  }
});

/**
 * Get server-specific secrets
 */
router.get('/server/:serverName', async (req: Request, res: Response): Promise<any> => {
  try {
    const { serverName } = req.params;
    const secrets = await secureConfig.getServerSecrets(serverName);
    
    // Mask secret values in response
    const maskedSecrets: Record<string, string> = {};
    for (const [key, value] of Object.entries(secrets)) {
      maskedSecrets[key] = value ? '***' : '<not set>';
    }
    
    res.json({
      server: serverName,
      secrets: maskedSecrets,
      count: Object.keys(secrets).length
    });
  } catch (error) {
    logger.error('Failed to get server secrets', { error, server: req.params.serverName });
    res.status(500).json({
      error: 'Failed to get server secrets'
    });
  }
});

/**
 * Get cache statistics
 */
router.get('/cache/stats', async (_req: Request, res: Response): Promise<any> => {
  try {
    const secretsManager = secureConfig.getSecretsManager();
    if (!secretsManager) {
      return res.status(503).json({
        error: 'Secrets manager not initialized'
      });
    }

    const stats = secretsManager.getCacheStats();
    
    res.json({
      ...stats,
      hits: 0, // Would need to track these
      misses: 0
    });
  } catch (error) {
    logger.error('Failed to get cache stats', { error });
    res.status(500).json({
      error: 'Failed to get cache statistics'
    });
  }
});

/**
 * Clear secrets cache
 */
router.post('/cache/clear', async (_req: Request, res: Response): Promise<any> => {
  try {
    await secureConfig.refreshSecrets();
    
    res.json({
      success: true,
      message: 'Secrets cache cleared'
    });
  } catch (error) {
    logger.error('Failed to clear cache', { error });
    res.status(500).json({
      error: 'Failed to clear secrets cache'
    });
  }
});

/**
 * Get audit log
 */
router.get('/audit', async (req: Request, res: Response): Promise<any> => {
  try {
    const secretsManager = secureConfig.getSecretsManager();
    if (!secretsManager) {
      return res.status(503).json({
        error: 'Secrets manager not initialized'
      });
    }

    const limit = parseInt(req.query.limit as string) || 100;
    const events = secretsManager.getAuditLog(limit);
    
    res.json({
      events,
      count: events.length,
      limit
    });
  } catch (error) {
    logger.error('Failed to get audit log', { error });
    res.status(500).json({
      error: 'Failed to get audit log'
    });
  }
});

/**
 * Health check for secrets system
 */
router.get('/health', async (_req: Request, res: Response): Promise<any> => {
  try {
    const secretsManager = secureConfig.getSecretsManager();
    if (!secretsManager) {
      return res.status(503).json({
        status: 'unhealthy',
        error: 'Secrets manager not initialized'
      });
    }

    const providers = secretsManager.getAvailableProviders();
    const healthy = providers.length > 0;
    
    res.status(healthy ? 200 : 503).json({
      status: healthy ? 'healthy' : 'unhealthy',
      providers: providers.length,
      cache: secretsManager.getCacheStats()
    });
  } catch (error) {
    logger.error('Health check failed', { error });
    res.status(503).json({
      status: 'unhealthy',
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

export default router;