import { useTranslation } from 'react-i18next'
import { useGraphStore } from '@/stores/graph'
import { D3_THEME } from '@/lib/d3GraphTheme'

export default function D3GraphLegend() {
  const { t } = useTranslation()
  const typeColorMap = useGraphStore.use.typeColorMap()

  if (!typeColorMap || typeColorMap.size === 0) {
    return null
  }

  return (
    <div
      className="absolute bottom-4 left-4 z-30 max-w-[220px] rounded-xl border border-gray-100 bg-white/95 p-3 shadow-[0_4px_20px_rgba(0,0,0,0.07)] backdrop-blur-sm"
      style={{ fontFamily: D3_THEME.graphFont }}
    >
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">
        {t('graphPanel.legend', 'Legend')}
      </h3>
      <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
        {Array.from(typeColorMap.entries()).map(([type, color]) => (
          <div key={type} className="flex items-center gap-2">
            <span
              className="size-3 shrink-0 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="truncate text-xs text-gray-700" title={type}>
              {t(`graphPanel.nodeTypes.${type.toLowerCase().replace(/\s+/g, '')}`, type)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
