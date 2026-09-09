/** Legacy route — knowledge graph now lives under each KB category. */
export function renderKnowledge() {
  return '';
}

export async function mountKnowledge() {
  location.hash = '#kb';
}
