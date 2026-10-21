import SiteHeader from './components/SiteHeader';
import { AuthProvider } from './context/AuthContext';
import { embeddedPackage } from './lib/target';
import ReleasesPage from './pages/ReleasesPage';
import './App.css';

// The read-only Release Notes page packaged into OFBiz: release history and version details only.
function ViewerApp() {
  const info = embeddedPackage().package;
  return (
    <AuthProvider>
      <span id="top" />
      <SiteHeader pathname="/" />
      <main className="site-main">
        <ReleasesPage />
        {info && (
          <p className="viewer-package-info">
            Release notes package {info.fileName}, generated {new Date(info.generatedAt).toLocaleString()}.
          </p>
        )}
      </main>
    </AuthProvider>
  );
}

export default ViewerApp;
