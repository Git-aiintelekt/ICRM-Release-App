import { apiFetch } from './apiClient';
import { OFBIZ_VIEWER, embeddedPackage } from '../lib/target';

export function getReleases() {
  // The OFBiz viewer has no server to ask: its releases are embedded in the page.
  if (OFBIZ_VIEWER) {
    return Promise.resolve(embeddedPackage().releases);
  }
  return apiFetch('/api/releases');
}
