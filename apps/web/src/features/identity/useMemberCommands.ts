import type { components } from '@scopesteps/api-client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { CURRENT_USER_KEY } from './useCurrentUser';
import type { GrantableRole } from './roleNames';

export type Invitation = components['schemas']['InvitationResponse'];
export type ProjectMember = components['schemas']['ProjectMemberResponse'];

function invitationsKey(projectId: string) {
  return ['identity', projectId, 'invitations'] as const;
}

function membersKey(projectId: string) {
  return ['identity', projectId, 'members'] as const;
}

/** The invitations nobody has accepted yet. Only an approver may read them. */
export function useInvitations(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: invitationsKey(projectId),
    enabled,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/invitations', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.invitations;
    },
  });
}

/**
 * Inviting, re-linking, emailing and cancelling invitations, and changing or removing members.
 * Each refreshes what it affects; the server checks every role and revision.
 */
export function useMemberCommands(projectId: string) {
  const queryClient = useQueryClient();
  const path = { project_id: projectId };
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: invitationsKey(projectId) }),
      queryClient.invalidateQueries({ queryKey: membersKey(projectId) }),
      queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
    ]);

  const invite = useMutation({
    mutationFn: async (body: { email: string; roles: GrantableRole[]; send_email: boolean }) => {
      const { data, error, response } = await api.POST('/api/v1/projects/{project_id}/members', {
        params: { path },
        body,
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSettled: refresh,
  });

  const newLink = useMutation({
    mutationFn: async (invitationId: string) => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/invitations/{invitation_id}/link',
        { params: { path: { ...path, invitation_id: invitationId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSettled: refresh,
  });

  const emailInvitation = useMutation({
    mutationFn: async (invitationId: string) => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/invitations/{invitation_id}/email',
        { params: { path: { ...path, invitation_id: invitationId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSettled: refresh,
  });

  const cancel = useMutation({
    mutationFn: async (invitationId: string) => {
      const { error, response } = await api.DELETE(
        '/api/v1/projects/{project_id}/invitations/{invitation_id}',
        { params: { path: { ...path, invitation_id: invitationId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSettled: refresh,
  });

  const changeRoles = useMutation({
    mutationFn: async (change: {
      userId: string;
      roles: GrantableRole[];
      expectedRevision: number;
    }) => {
      const { data, error, response } = await api.PUT(
        '/api/v1/projects/{project_id}/members/{user_id}/roles',
        {
          params: { path: { ...path, user_id: change.userId } },
          body: { roles: change.roles, expected_revision: change.expectedRevision },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSettled: () =>
      Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: CURRENT_USER_KEY })]),
  });

  const remove = useMutation({
    mutationFn: async (userId: string) => {
      const { error, response } = await api.DELETE(
        '/api/v1/projects/{project_id}/members/{user_id}',
        { params: { path: { ...path, user_id: userId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSettled: refresh,
  });

  return { invite, newLink, emailInvitation, cancel, changeRoles, remove };
}
