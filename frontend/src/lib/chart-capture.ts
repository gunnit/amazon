/**
 * Capture Recharts SVG containers as base64 PNG images for PDF export.
 *
 * Recharts uses CSS custom properties (e.g. `hsl(var(--primary))`) which
 * are not portable outside the DOM. This utility resolves all computed
 * styles and inlines them before serializing the SVG, then draws it
 * onto a canvas at 2x resolution for retina-quality output.
 */

const SCALE = 2 // 2x resolution for sharp charts on PDF

/**
 * Force light-mode colors on a container by temporarily overriding
 * CSS custom properties. Returns a cleanup function.
 */
function forceLightMode(container: HTMLElement): () => void {
  const lightVars: Record<string, string> = {
    '--background': '0 0% 100%',
    '--foreground': '222.2 84% 4.9%',
    '--primary': '221.2 83.2% 53.3%',
    '--primary-foreground': '210 40% 98%',
    '--muted': '210 40% 96.1%',
    '--muted-foreground': '215.4 16.3% 46.9%',
    '--destructive': '0 84.2% 60.2%',
    '--border': '214.3 31.8% 91.4%',
  }

  const originals: Record<string, string> = {}
  for (const [key, value] of Object.entries(lightVars)) {
    originals[key] = container.style.getPropertyValue(key)
    container.style.setProperty(key, value)
  }

  return () => {
    for (const [key, original] of Object.entries(originals)) {
      if (original) {
        container.style.setProperty(key, original)
      } else {
        container.style.removeProperty(key)
      }
    }
  }
}

/**
 * Capture a chart container's SVG as a base64-encoded PNG string.
 *
 * @param container - The DOM element wrapping a Recharts `ResponsiveContainer`
 * @returns base64 string (without data URI prefix) or null if capture fails
 */
export async function captureChartAsBase64(
  container: HTMLElement | null,
): Promise<string | null> {
  if (!container) return null

  const svg = container.querySelector('svg')
  if (!svg) return null

  // Force light mode for consistent PDF output
  const restoreColors = forceLightMode(container)

  // Wait a frame for styles to apply
  await new Promise((r) => requestAnimationFrame(r))

  try {
    // Clone SVG so we don't mutate the original
    const clone = svg.cloneNode(true) as SVGSVGElement

    // Inline computed styles on the clone (read from original which has light-mode)
    inlineStylesFromSource(svg, clone)

    // Set explicit dimensions
    const bbox = svg.getBoundingClientRect()
    const width = bbox.width
    const height = bbox.height
    clone.setAttribute('width', String(width))
    clone.setAttribute('height', String(height))
    clone.setAttribute('viewBox', `0 0 ${width} ${height}`)

    // Set white background
    clone.style.backgroundColor = 'white'
    const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
    bgRect.setAttribute('width', '100%')
    bgRect.setAttribute('height', '100%')
    bgRect.setAttribute('fill', 'white')
    clone.insertBefore(bgRect, clone.firstChild)

    // Serialize
    const serializer = new XMLSerializer()
    const svgString = serializer.serializeToString(clone)
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(svgBlob)

    // Draw to canvas
    const canvas = document.createElement('canvas')
    canvas.width = width * SCALE
    canvas.height = height * SCALE
    const ctx = canvas.getContext('2d')!
    ctx.scale(SCALE, SCALE)

    return new Promise<string | null>((resolve) => {
      const img = new window.Image()
      img.onload = () => {
        ctx.drawImage(img, 0, 0, width, height)
        URL.revokeObjectURL(url)
        // Get base64 without the "data:image/png;base64," prefix
        const dataUrl = canvas.toDataURL('image/png')
        const base64 = dataUrl.split(',')[1] || null
        resolve(base64)
      }
      img.onerror = () => {
        URL.revokeObjectURL(url)
        resolve(null)
      }
      img.src = url
    })
  } finally {
    restoreColors()
  }
}

/**
 * Inline computed styles from `source` SVG elements onto matching
 * elements in `target` (cloned) SVG.
 */
function inlineStylesFromSource(source: SVGSVGElement, target: SVGSVGElement) {
  const sourceEls = source.querySelectorAll('*')
  const targetEls = target.querySelectorAll('*')

  sourceEls.forEach((srcEl, i) => {
    const tgtEl = targetEls[i]
    if (!tgtEl) return

    const computed = window.getComputedStyle(srcEl)
    const styleProps = ['fill', 'stroke', 'color', 'stop-color', 'opacity'] as const
    styleProps.forEach((prop) => {
      const value = computed.getPropertyValue(prop)
      if (value && value !== 'none' && value !== '' && value !== 'inherit') {
        ;(tgtEl as SVGElement).style.setProperty(prop, value)
      }
    })

    if (srcEl.tagName === 'text' || srcEl.tagName === 'tspan') {
      const fontProps = ['font-size', 'font-family', 'font-weight', 'text-anchor'] as const
      fontProps.forEach((prop) => {
        const value = computed.getPropertyValue(prop)
        if (value) {
          ;(tgtEl as SVGElement).style.setProperty(prop, value)
        }
      })
    }
  })
}

/**
 * Capture multiple chart containers at once.
 *
 * @param refs - Map of chart name to container element
 * @returns Map of chart name to base64 PNG string
 */
export async function captureAllCharts(
  refs: Record<string, HTMLElement | null>,
): Promise<Record<string, string>> {
  const result: Record<string, string> = {}

  for (const [key, container] of Object.entries(refs)) {
    const base64 = await captureChartAsBase64(container)
    if (base64) {
      result[key] = base64
    }
  }

  return result
}
