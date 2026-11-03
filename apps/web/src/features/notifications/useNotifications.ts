import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { CHECK_EVERY_MS, NOTIFICATIONS_KEY } from './types';
import type { NotificationSettings } from './types';

const SETTINGS_KEY = [...NOTIFICATIONS_KEY, 'settings'] as const;

/** Checked every 30 seconds; TanStack Query pauses that while the tab is hidden. */
export function useUnreadCount() {
  return useQuery({
    queryKey: [...NOTIFICATIONS_KEY, 'unread-count'],
    refetchInterval: CHECK_EVERY_MS,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me/notifications/unread-count');
      if (error) {
        throw toApiError(error, response);
      }
      return data.unread;
    },
  });
}

export function useNotificationList(enabled: boolean) {
  return useQuery({
    queryKey: [...NOTIFICATIONS_KEY, 'list'],
    enabled,
    refetchInterval: enabled ? CHECK_EVERY_MS : false,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me/notifications');
      if (error) {
        throw toApiError(error, response);
      }
      return data.notifications;
    },
  });
}

export function useNotificationCommands() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
  const read = useMutation({
    mutationFn: async (notificationId: string) => {
      const { error, response } = await api.POST(
        '/api/v1/me/notifications/{notification_id}/read',
        { params: { path: { notification_id: notificationId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSettled: refresh,
  });
  const readAll = useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST('/api/v1/me/notifications/read-all');
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSettled: refresh,
  });
  return { read, readAll };
}

export function useNotificationSettings() {
  return useQuery({
    queryKey: SETTINGS_KEY,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me/notification-settings');
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}

export function useSaveNotificationSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (settings: NotificationSettings) => {
      const { data, error, response } = await api.PUT('/api/v1/me/notification-settings', {
        body: settings,
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(SETTINGS_KEY, saved);
    },
  });
}
