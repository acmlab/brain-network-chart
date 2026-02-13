import { useState } from 'react'
import type { ResultItem } from './types'
import ResultsQueue from './components/results/ResultsQueue'
import FileManager from './components/FileManager'
import StatsFormPanel from './components/StatsFormPanel'

export default function App() {
  const [results, setResults] = useState<ResultItem[]>([])

  function addResult(item: ResultItem) {
    setResults(prev => [item, ...prev])
  }

  return (
    <div className="app">
      <div className="panel panel-left">
        <div className="panel-title">Visualization Results</div>
        {results.length === 0 ? (
          <div className="empty-state">
            Run a stats tool on the right to see results here
          </div>
        ) : (
          <ResultsQueue results={results} />
        )}
      </div>
      <div className="panel panel-right">
        <div className="panel-title">Brain Network Stats</div>
        <FileManager />
        <StatsFormPanel onResult={addResult} />
      </div>
    </div>
  )
}
