type Listener = () => void;

const listeners = new Set<Listener>();

/**
 * Calls `listener` whenever the API answers 401 to a request other than sign-in: the session
 * is missing, has expired or was signed out elsewhere. Returns a function that unsubscribes.
 */
export function onSessionEnded(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function reportSessionEnded(): void {
  for (const listener of [...listeners]) {
    listener();
  }
}
