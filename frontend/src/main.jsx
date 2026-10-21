import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ViewerApp from './ViewerApp.jsx'
import { OFBIZ_VIEWER } from './lib/target'

const Root = OFBIZ_VIEWER ? ViewerApp : App

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
