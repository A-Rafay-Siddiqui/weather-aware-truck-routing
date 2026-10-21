import { useEffect, useState } from 'react';

/** True once `active` has stayed true for `afterMs`, so long waits can be explained. */
export function useSlowFlag(active: boolean, afterMs: number) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const id = window.setTimeout(() => setSlow(true), afterMs);
    return () => window.clearTimeout(id);
  }, [active, afterMs]);
  return slow;
}
