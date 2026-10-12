import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';

export function useApiHealth() {
  return useQuery({
    queryKey: ['health', 'ready'],
    queryFn: async () => {
      const { data, error } = await api.GET('/health/ready');
      if (error) {
        throw new Error('API is not ready');
      }
      return data;
    },
    retry: false,
  });
}
