/**
 * API service for job role management.
 */

import type { JobRole, JobRoleCreate, JobRoleUpdate, JobRoleListResponse } from '../types';

const API_BASE = '/api';

/**
 * Get all job roles.
 */
export async function listRoles(activeOnly: boolean = true): Promise<JobRoleListResponse> {
  const params = new URLSearchParams();
  if (activeOnly) {
    params.set('active_only', 'true');
  }

  const response = await fetch(`${API_BASE}/admin/roles/?${params.toString()}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch roles: ${response.status}`);
  }

  return response.json();
}

/**
 * Get a specific job role by ID.
 */
export async function getRole(roleId: string): Promise<JobRole> {
  const response = await fetch(`${API_BASE}/admin/roles/${roleId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to fetch role: ${response.status}`);
  }

  return response.json();
}

/**
 * Create a new job role.
 */
export async function createRole(role: JobRoleCreate): Promise<JobRole> {
  const response = await fetch(`${API_BASE}/admin/roles/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(role),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to create role: ${response.status}`);
  }

  return response.json();
}

/**
 * Update an existing job role.
 */
export async function updateRole(roleId: string, updates: JobRoleUpdate): Promise<JobRole> {
  const response = await fetch(`${API_BASE}/admin/roles/${roleId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(updates),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to update role: ${response.status}`);
  }

  return response.json();
}

/**
 * Delete a job role.
 */
export async function deleteRole(roleId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/admin/roles/${roleId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `Failed to delete role: ${response.status}`);
  }
}
