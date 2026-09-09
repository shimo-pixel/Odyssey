import { X } from 'lucide-react'
import type { LightragGraphType } from '@/api/lightrag'
import {
  D3_THEME,
  getNodeLabel,
  getNodeType,
  isMonoPropertyKey
} from '@/lib/d3GraphTheme'
import { useTranslation } from 'react-i18next'

interface D3NodeDetailPanelProps {
  node: LightragGraphType['nodes'][number]
  entityColor: string
  onClose: () => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

const RESERVED_KEYS = new Set(['entity_id', 'entity_type', 'description', 'name'])

export default function D3NodeDetailPanel({
  node,
  entityColor,
  onClose,
  onMouseEnter,
  onMouseLeave
}: D3NodeDetailPanelProps) {
  const { t } = useTranslation()
  const title = getNodeLabel(node)
  const entityType = getNodeType(node)
  const properties = node.properties ?? {}

  const extraEntries = Object.entries(properties).filter(
    ([key, value]) =>
      !RESERVED_KEYS.has(key) &&
      value !== null &&
      value !== undefined &&
      String(value).trim() !== ''
  )

  return (
    <aside
      className="absolute top-3 right-3 z-30 flex w-[320px] max-h-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-[10px] border border-gray-100 bg-white shadow-[0_4px_24px_rgba(0,0,0,0.08)]"
      style={{ fontFamily: D3_THEME.detailFont }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="flex items-start justify-between gap-2 border-b border-gray-100 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: entityColor }}
            />
            <h2 className="truncate text-base font-semibold text-gray-900">{title}</h2>
          </div>
          <p className="mt-1 text-xs text-gray-500">{entityType}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700"
          aria-label={t('graphPanel.d3.closeDetail', 'Close')}
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 text-sm leading-relaxed text-gray-700">
        {properties.description && (
          <section className="mb-4">
            <h3 className="mb-1 text-xs font-medium text-gray-400 uppercase">
              {t('graphPanel.d3.description', 'Description')}
            </h3>
            <p className="text-sm text-gray-700">{String(properties.description)}</p>
          </section>
        )}

        <section className="space-y-2">
          <h3 className="text-xs font-medium text-gray-400 uppercase">
            {t('graphPanel.d3.properties', 'Properties')}
          </h3>
          <dl className="space-y-2">
            <div>
              <dt className="text-xs text-gray-400">ID</dt>
              <dd
                className="mt-0.5 break-all text-xs text-gray-600"
                style={{ fontFamily: D3_THEME.monoFont }}
              >
                {node.id}
              </dd>
            </div>
            {extraEntries.map(([key, value]) => (
              <div key={key}>
                <dt className="text-xs text-gray-400">{key}</dt>
                <dd
                  className="mt-0.5 break-all text-xs text-gray-600"
                  style={{
                    fontFamily: isMonoPropertyKey(key)
                      ? D3_THEME.monoFont
                      : D3_THEME.detailFont
                  }}
                >
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
    </aside>
  )
}
