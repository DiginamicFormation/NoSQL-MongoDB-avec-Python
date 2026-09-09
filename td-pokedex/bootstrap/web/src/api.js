// Le seul endroit qui parle a l'API. URL relatives : nginx proxifie /api.

async function appeler(chemin, options = {}) {
  const reponse = await fetch(`/api${chemin}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (reponse.status === 204) return null;
  const corps = await reponse.json().catch(() => ({}));
  if (!reponse.ok) {
    throw new Error(corps.erreur ?? `erreur ${reponse.status}`);
  }
  return corps;
}

export const api = {
  sante: () => appeler('/sante'),

  lister: ({ famille, q, eteintes, apres, taille = 100 } = {}) => {
    const p = new URLSearchParams();
    if (famille) p.set('famille', famille);
    if (q) p.set('q', q);
    if (eteintes) p.set('eteintes', '1');
    if (apres != null) p.set('apres', apres);
    p.set('taille', taille);
    return appeler(`/especes?${p}`);
  },

  fiche: (numero) => appeler(`/especes/${numero}`),

  creer: (espece) => appeler('/especes', {
    method: 'POST',
    body: JSON.stringify(espece),
  }),

  modifier: (numero, champs) => appeler(`/especes/${numero}`, {
    method: 'PATCH',
    body: JSON.stringify({ champs }),
  }),

  evoluer: (numero) => appeler(`/especes/${numero}/evolution`, { method: 'POST' }),

  eteindre: (numero, definitif = false) =>
    appeler(`/especes/${numero}?definitif=${definitif ? 1 : 0}`, { method: 'DELETE' }),

  restaurer: (numero) =>
    appeler(`/especes/${numero}/restauration`, { method: 'POST' }),

  // GeoJSON, donc [longitude, latitude] - l'inverse de Leaflet.
  autour: (lon, lat, km) => appeler(`/autour?lon=${lon}&lat=${lat}&km=${km}`),

  zone: ({ ouest, sud, est, nord }) =>
    appeler(`/zone?ouest=${ouest}&sud=${sud}&est=${est}&nord=${nord}`),

  statistiques: () => appeler('/statistiques'),
  audit: () => appeler('/audit'),
  schema: () => appeler('/schema'),
};

export const STADES = ['junior', 'mature', 'senior', 'gourou'];

export const COULEURS = {
  backend: '#2f6f4f',
  frontend: '#8a4b9c',
  data: '#1f6f8b',
  securite: '#a63d40',
  infra: '#b8762a',
};
