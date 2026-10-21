import { AuditTab } from './SettingsPage';

// The same audit log as Settings → Audit log, as its own page in the navigation.
function AuditLogPage() {
  return (
    <div className="page settings-page">
      <section className="page-hero">
        <p className="eyebrow">Admin</p>
        <h1>Audit logs</h1>
        <p className="page-lede">Who signed in, what they opened, and every administrative change.</p>
      </section>
      <AuditTab />
    </div>
  );
}

export default AuditLogPage;
