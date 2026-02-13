import type { ResultItem } from '../../types'
import CorrelationCard from './CorrelationCard'
import GroupComparisonCard from './GroupComparisonCard'
import FDRCorrectionCard from './FDRCorrectionCard'
import OutlierDetectionCard from './OutlierDetectionCard'
import CFCWaveletCard from './CFCWaveletCard'
import HubDetectionCard from './HubDetectionCard'
import GrowthCurveCard from './GrowthCurveCard'

interface Props {
  results: ResultItem[]
}

export default function ResultsQueue({ results }: Props) {
  return (
    <>
      {results.map(item => {
        switch (item.type) {
          case 'correlation':
            return <CorrelationCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'group_comparison':
            return <GroupComparisonCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'fdr_correction':
            return <FDRCorrectionCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'outliers':
            return <OutlierDetectionCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'cfc_wavelet':
            return <CFCWaveletCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'hub_detection':
            return <HubDetectionCard key={item.id} data={item.data} timestamp={item.timestamp} />
          case 'growth_curve':
            return <GrowthCurveCard key={item.id} data={item.data} timestamp={item.timestamp} />
        }
      })}
    </>
  )
}
