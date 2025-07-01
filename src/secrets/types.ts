/**
 * Types for secrets management
 */

import { z } from 'zod';

/**
 * Supported secret providers
 */
export enum SecretProvider {
  ENVIRONMENT = 'environment',
  ONEPASSWORD = '1password',
  AWS_SECRETS_MANAGER = 'aws-secrets-manager',
  HASHICORP_VAULT = 'hashicorp-vault',
  AZURE_KEY_VAULT = 'azure-key-vault',
}

/**
 * Secret metadata
 */
export interface SecretMetadata {
  name: string;
  provider: SecretProvider;
  path?: string; // Provider-specific path (e.g., vault path, 1Password item)
  version?: string;
  lastUpdated?: Date;
  ttl?: number; // Time to live in seconds
}

/**
 * Secret value with metadata
 */
export interface Secret {
  value: string;
  metadata: SecretMetadata;
  expiresAt?: Date;
}

/**
 * Secret reference in configuration
 */
export interface SecretReference {
  provider: SecretProvider;
  path: string;
  field?: string; // For providers that support fields (e.g., 1Password)
  version?: string;
}

/**
 * Cache entry for secrets
 */
export interface SecretCacheEntry {
  secret: Secret;
  fetchedAt: Date;
  accessCount: number;
}

/**
 * Secret provider configuration
 */
export interface SecretProviderConfig {
  provider: SecretProvider;
  enabled: boolean;
  config?: Record<string, any>;
}

/**
 * 1Password configuration schema
 */
export const OnePasswordConfigSchema = z.object({
  vault: z.string().optional().describe('Default 1Password vault name'),
  allowedVaults: z.array(z.string()).optional().describe('List of allowed vaults'),
  serviceAccountToken: z.string().optional().describe('1Password service account token'),
  connectHost: z.string().optional().describe('1Password Connect server URL'),
  connectToken: z.string().optional().describe('1Password Connect token'),
  cliPath: z.string().default('op').describe('Path to 1Password CLI'),
  cacheTtl: z.number().default(300).describe('Cache TTL in seconds'),
});

export type OnePasswordConfig = z.infer<typeof OnePasswordConfigSchema>;

/**
 * Secrets configuration schema
 */
export const SecretsConfigSchema = z.object({
  defaultProvider: z.nativeEnum(SecretProvider).default(SecretProvider.ENVIRONMENT),
  providers: z.array(z.object({
    type: z.nativeEnum(SecretProvider),
    enabled: z.boolean().default(true),
    config: z.record(z.any()).optional(),
  })).default([]),
  cache: z.object({
    enabled: z.boolean().default(true),
    maxSize: z.number().default(100),
    ttl: z.number().default(300), // 5 minutes
  }).default({}),
  audit: z.object({
    enabled: z.boolean().default(false),
    logAccess: z.boolean().default(false),
    logRotation: z.boolean().default(true),
  }).default({}),
});

export type SecretsConfig = z.infer<typeof SecretsConfigSchema>;

/**
 * Secret access audit event
 */
export interface SecretAuditEvent {
  timestamp: Date;
  action: 'access' | 'rotate' | 'create' | 'delete';
  secretName: string;
  provider: SecretProvider;
  accessor?: string;
  success: boolean;
  error?: string;
}

/**
 * Interface for secret providers
 */
export interface ISecretProvider {
  readonly name: SecretProvider;
  
  /**
   * Initialize the provider
   */
  initialize(): Promise<void>;
  
  /**
   * Get a secret value
   */
  getSecret(path: string, field?: string): Promise<Secret>;
  
  /**
   * Set a secret value (if supported)
   */
  setSecret?(path: string, value: string, field?: string): Promise<void>;
  
  /**
   * Delete a secret (if supported)
   */
  deleteSecret?(path: string, field?: string): Promise<void>;
  
  /**
   * List available secrets (if supported)
   */
  listSecrets?(prefix?: string): Promise<SecretMetadata[]>;
  
  /**
   * Rotate a secret (if supported)
   */
  rotateSecret?(path: string, field?: string): Promise<Secret>;
  
  /**
   * Check if provider is available
   */
  isAvailable(): Promise<boolean>;
  
  /**
   * Shutdown the provider
   */
  shutdown(): Promise<void>;
}

/**
 * Errors for secrets management
 */
export class SecretError extends Error {
  constructor(
    message: string,
    public readonly provider: SecretProvider,
    public readonly code: string,
    public readonly cause?: Error
  ) {
    super(message);
    this.name = 'SecretError';
  }
}

export class SecretNotFoundError extends SecretError {
  constructor(path: string, provider: SecretProvider) {
    super(`Secret not found: ${path}`, provider, 'SECRET_NOT_FOUND');
  }
}

export class SecretProviderError extends SecretError {
  constructor(message: string, provider: SecretProvider, cause?: Error) {
    super(message, provider, 'PROVIDER_ERROR', cause);
  }
}

export class SecretAccessDeniedError extends SecretError {
  constructor(path: string, provider: SecretProvider) {
    super(`Access denied to secret: ${path}`, provider, 'ACCESS_DENIED');
  }
}