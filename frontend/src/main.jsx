// import React from 'react'
// import ReactDOM from 'react-dom/client'
// import App from './App_test1.jsx'
// import './index.css'

// ReactDOM.createRoot(document.getElementById('root')).render(
//   <React.StrictMode>
//     <App />
//   </React.StrictMode>,
// )

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App_test1.jsx'
import './index.css'
import { CopilotKit } from '@copilotkit/react-core'
import '@copilotkit/react-ui/styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <CopilotKit runtimeUrl="http://localhost:4000/copilotkit" agent="root_agent">
      <App />
    </CopilotKit>
  </React.StrictMode>,
)