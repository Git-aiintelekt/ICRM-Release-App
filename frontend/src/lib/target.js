// true in the read-only viewer packaged into OFBiz (npm run build:ofbiz). The release data is embedded in the
// page by the OFBiz package generator as window.__RELEASE_NOTES__ = { releases, package: {...}, homeUrl }.
export const OFBIZ_VIEWER = import.meta.env.MODE === 'ofbiz';

export function embeddedPackage() {
  return (typeof window !== 'undefined' && window.__RELEASE_NOTES__) || { releases: [] };
}
