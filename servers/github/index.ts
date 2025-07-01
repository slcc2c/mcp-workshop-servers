/**
 * GitHub MCP Server
 * Provides comprehensive GitHub repository management capabilities
 */

import { Octokit } from '@octokit/rest';
import { z } from 'zod';
import { BaseMCPServer, createToolHandler } from '../../src/core/base-server';
import { config } from '../../src/utils/config';

// Input schemas
const RepoSchema = z.object({
  owner: z.string().describe('Repository owner'),
  repo: z.string().describe('Repository name'),
});

const CreateRepoSchema = z.object({
  name: z.string().describe('Repository name'),
  description: z.string().optional().describe('Repository description'),
  private: z.boolean().default(false).describe('Create as private repository'),
  autoInit: z.boolean().default(true).describe('Initialize with README'),
});

const CreateIssueSchema = z.object({
  owner: z.string().describe('Repository owner'),
  repo: z.string().describe('Repository name'),
  title: z.string().describe('Issue title'),
  body: z.string().optional().describe('Issue body'),
  labels: z.array(z.string()).optional().describe('Issue labels'),
  assignees: z.array(z.string()).optional().describe('Issue assignees'),
});

const CreatePRSchema = z.object({
  owner: z.string().describe('Repository owner'),
  repo: z.string().describe('Repository name'),
  title: z.string().describe('Pull request title'),
  body: z.string().optional().describe('Pull request body'),
  head: z.string().describe('Source branch'),
  base: z.string().default('main').describe('Target branch'),
});

const CloneRepoSchema = z.object({
  owner: z.string().describe('Repository owner'),
  repo: z.string().describe('Repository name'),
  path: z.string().describe('Local path to clone to'),
  branch: z.string().optional().describe('Branch to clone'),
});

export class GitHubServer extends BaseMCPServer {
  private octokit!: Octokit;

  constructor() {
    super('github', '1.0.0', 'GitHub integration for repository management');
  }

  protected async onInitialize(): Promise<void> {
    const token = config.getGitHubToken();
    if (!token) {
      throw new Error('GitHub token not configured. Set GITHUB_TOKEN environment variable.');
    }

    this.octokit = new Octokit({
      auth: token,
      userAgent: 'mcp-workshop-github/1.0.0',
    });

    // Test authentication
    try {
      const { data: user } = await this.octokit.users.getAuthenticated();
      this.logger.info('GitHub authenticated', { user: user.login });
    } catch (error) {
      this.logger.error('GitHub authentication failed', { error });
      throw new Error('Failed to authenticate with GitHub');
    }
  }

  protected async onShutdown(): Promise<void> {
    // Nothing to clean up
  }

  protected async registerTools(): Promise<void> {
    // Repository management
    this.registerTool(
      'github_get_repo',
      'Get repository information',
      RepoSchema,
      createToolHandler<z.infer<typeof RepoSchema>>(async ({ owner, repo }) => {
        const { data } = await this.octokit.repos.get({ owner, repo });
        return {
          name: data.name,
          description: data.description,
          private: data.private,
          stars: data.stargazers_count,
          forks: data.forks_count,
          language: data.language,
          defaultBranch: data.default_branch,
          url: data.html_url,
          cloneUrl: data.clone_url,
        };
      })
    );

    this.registerTool(
      'github_create_repo',
      'Create a new repository',
      CreateRepoSchema,
      createToolHandler<z.infer<typeof CreateRepoSchema>>(async ({ name, description, private: isPrivate, autoInit }) => {
        const { data: user } = await this.octokit.users.getAuthenticated();
        const { data } = await this.octokit.repos.createForAuthenticatedUser({
          name,
          description,
          private: isPrivate,
          auto_init: autoInit,
        });
        return {
          name: data.name,
          url: data.html_url,
          cloneUrl: data.clone_url,
          owner: user.login,
        };
      })
    );

    this.registerTool(
      'github_list_repos',
      'List repositories for authenticated user',
      z.object({
        type: z.enum(['all', 'owner', 'member']).default('owner'),
        sort: z.enum(['created', 'updated', 'pushed', 'full_name']).default('updated'),
        perPage: z.number().min(1).max(100).default(30),
      }),
      createToolHandler<{ type: 'all' | 'owner' | 'member'; sort: 'created' | 'updated' | 'pushed' | 'full_name'; perPage: number }>(async ({ type, sort, perPage }) => {
        const { data } = await this.octokit.repos.listForAuthenticatedUser({
          type,
          sort,
          per_page: perPage,
        });
        return data.map(repo => ({
          name: repo.name,
          fullName: repo.full_name,
          description: repo.description,
          private: repo.private,
          url: repo.html_url,
          updatedAt: repo.updated_at,
        }));
      })
    );

    // Issues
    this.registerTool(
      'github_create_issue',
      'Create a new issue',
      CreateIssueSchema,
      createToolHandler<z.infer<typeof CreateIssueSchema>>(async ({ owner, repo, title, body, labels, assignees }) => {
        const { data } = await this.octokit.issues.create({
          owner,
          repo,
          title,
          body,
          labels,
          assignees,
        });
        return {
          number: data.number,
          title: data.title,
          url: data.html_url,
          state: data.state,
        };
      })
    );

    this.registerTool(
      'github_list_issues',
      'List repository issues',
      z.object({
        owner: z.string(),
        repo: z.string(),
        state: z.enum(['open', 'closed', 'all']).default('open'),
        labels: z.string().optional().describe('Comma-separated list of labels'),
        sort: z.enum(['created', 'updated', 'comments']).default('created'),
        perPage: z.number().min(1).max(100).default(30),
      }),
      createToolHandler<{ owner: string; repo: string; state: 'open' | 'closed' | 'all'; labels?: string; sort: 'created' | 'updated' | 'comments'; perPage: number }>(async ({ owner, repo, state, labels, sort, perPage }) => {
        const { data } = await this.octokit.issues.listForRepo({
          owner,
          repo,
          state,
          labels,
          sort,
          per_page: perPage,
        });
        return data.map(issue => ({
          number: issue.number,
          title: issue.title,
          state: issue.state,
          url: issue.html_url,
          author: issue.user?.login,
          createdAt: issue.created_at,
          updatedAt: issue.updated_at,
          labels: issue.labels.map(l => typeof l === 'string' ? l : l.name),
        }));
      })
    );

    // Pull Requests
    this.registerTool(
      'github_create_pr',
      'Create a pull request',
      CreatePRSchema,
      createToolHandler<z.infer<typeof CreatePRSchema>>(async ({ owner, repo, title, body, head, base }) => {
        const { data } = await this.octokit.pulls.create({
          owner,
          repo,
          title,
          body,
          head,
          base,
        });
        return {
          number: data.number,
          title: data.title,
          url: data.html_url,
          state: data.state,
          draft: data.draft,
        };
      })
    );

    // Branches
    this.registerTool(
      'github_list_branches',
      'List repository branches',
      RepoSchema,
      createToolHandler<z.infer<typeof RepoSchema>>(async ({ owner, repo }) => {
        const { data } = await this.octokit.repos.listBranches({
          owner,
          repo,
          per_page: 100,
        });
        return data.map(branch => ({
          name: branch.name,
          protected: branch.protected,
          commit: branch.commit.sha,
        }));
      })
    );

    this.registerTool(
      'github_create_branch',
      'Create a new branch',
      z.object({
        owner: z.string(),
        repo: z.string(),
        branch: z.string().describe('New branch name'),
        from: z.string().default('main').describe('Source branch or commit SHA'),
      }),
      createToolHandler<{ owner: string; repo: string; branch: string; from: string }>(async ({ owner, repo, branch, from }) => {
        // Get the SHA of the source
        const { data: ref } = await this.octokit.git.getRef({
          owner,
          repo,
          ref: `heads/${from}`,
        });

        // Create new branch
        const { data } = await this.octokit.git.createRef({
          owner,
          repo,
          ref: `refs/heads/${branch}`,
          sha: ref.object.sha,
        });

        return {
          branch,
          sha: data.object.sha,
          url: data.url,
        };
      })
    );

    // Commits
    this.registerTool(
      'github_list_commits',
      'List repository commits',
      z.object({
        owner: z.string(),
        repo: z.string(),
        sha: z.string().optional().describe('Branch or commit SHA'),
        perPage: z.number().min(1).max(100).default(30),
      }),
      createToolHandler<{ owner: string; repo: string; sha?: string; perPage: number }>(async ({ owner, repo, sha, perPage }) => {
        const { data } = await this.octokit.repos.listCommits({
          owner,
          repo,
          sha,
          per_page: perPage,
        });
        return data.map(commit => ({
          sha: commit.sha,
          message: commit.commit.message,
          author: commit.commit.author?.name,
          date: commit.commit.author?.date,
          url: commit.html_url,
        }));
      })
    );

    // Clone repository (using git command)
    this.registerTool(
      'github_clone_repo',
      'Clone a repository to local filesystem',
      CloneRepoSchema,
      createToolHandler<z.infer<typeof CloneRepoSchema>>(async ({ owner, repo, path, branch }) => {
        const { data } = await this.octokit.repos.get({ owner, repo });
        const cloneUrl = data.clone_url;
        
        // This would need to execute git clone command
        // For now, return the command that would be executed
        return {
          command: `git clone ${branch ? `-b ${branch} ` : ''}${cloneUrl} ${path}`,
          cloneUrl,
          path,
          note: 'Execute this command to clone the repository',
        };
      })
    );

    // Workflow runs
    this.registerTool(
      'github_list_workflow_runs',
      'List GitHub Actions workflow runs',
      z.object({
        owner: z.string(),
        repo: z.string(),
        status: z.enum(['completed', 'action_required', 'cancelled', 'failure', 'neutral', 'skipped', 'stale', 'success', 'timed_out', 'in_progress', 'queued', 'requested', 'waiting']).optional(),
        perPage: z.number().min(1).max(100).default(10),
      }),
      createToolHandler<{ owner: string; repo: string; status?: 'completed' | 'action_required' | 'cancelled' | 'failure' | 'neutral' | 'skipped' | 'stale' | 'success' | 'timed_out' | 'in_progress' | 'queued' | 'requested' | 'waiting'; perPage: number }>(async ({ owner, repo, status, perPage }) => {
        const { data } = await this.octokit.actions.listWorkflowRunsForRepo({
          owner,
          repo,
          status,
          per_page: perPage,
        });
        return data.workflow_runs.map(run => ({
          id: run.id,
          name: run.name,
          status: run.status,
          conclusion: run.conclusion,
          createdAt: run.created_at,
          url: run.html_url,
        }));
      })
    );
  }

  protected getCustomMethods(): string[] {
    return ['searchCode', 'searchIssues', 'getUser'];
  }

  protected async handleCustomMethod(method: string, params: unknown): Promise<unknown> {
    switch (method) {
      case 'searchCode':
        return this.searchCode(params as any);
      case 'searchIssues':
        return this.searchIssues(params as any);
      case 'getUser':
        return this.getUser();
      default:
        return super.handleCustomMethod(method, params);
    }
  }

  private async searchCode(params: { query: string; perPage?: number }) {
    const { data } = await this.octokit.search.code({
      q: params.query,
      per_page: params.perPage || 30,
    });
    return {
      totalCount: data.total_count,
      items: data.items.map(item => ({
        name: item.name,
        path: item.path,
        repository: item.repository.full_name,
        url: item.html_url,
      })),
    };
  }

  private async searchIssues(params: { query: string; perPage?: number }) {
    const { data } = await this.octokit.search.issuesAndPullRequests({
      q: params.query,
      per_page: params.perPage || 30,
    });
    return {
      totalCount: data.total_count,
      items: data.items.map(item => ({
        number: item.number,
        title: item.title,
        state: item.state,
        url: item.html_url,
        repository: item.repository_url.split('/').slice(-2).join('/'),
      })),
    };
  }

  private async getUser() {
    const { data } = await this.octokit.users.getAuthenticated();
    return {
      login: data.login,
      name: data.name,
      email: data.email,
      publicRepos: data.public_repos,
      privateRepos: data.total_private_repos,
      followers: data.followers,
      following: data.following,
    };
  }
}