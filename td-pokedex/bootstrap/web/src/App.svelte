<script>
  import { api, COULEURS, STADES } from './api.js';
  import Carte from './Carte.svelte';
  import Fiche from './Fiche.svelte';

  const FAMILLES = ['backend', 'frontend', 'data', 'securite', 'infra'];

  let onglet = $state('catalogue');
  let especes = $state([]);
  let sante = $state(null);
  let erreur = $state('');
  let selection = $state(null);

  let famille = $state('');
  let recherche = $state('');
  let eteintes = $state(false);
  let rayonKm = $state(50);
  let filtreGeo = $state(null);        // {type:'autour'|'zone', libelle}

  let stats = $state([]);
  let audit = $state([]);
  let schema = $state(null);

  let creation = $state(false);
  let nouvelle = $state({ numero: '', nom: '', famille: 'backend', langages: '' });

  async function rafraichir() {
    erreur = '';
    try {
      sante = await api.sante();
    } catch (e) {
      sante = null;
    }
    try {
      if (filtreGeo) {
        especes = await filtreGeo.charger();
      } else {
        especes = await api.lister({ famille, q: recherche, eteintes });
      }
    } catch (e) {
      erreur = e.message;
    }
  }

  $effect(() => {
    famille; recherche; eteintes; filtreGeo;
    rafraichir();
  });

  async function ouvrirStats() {
    onglet = 'statistiques';
    try { stats = await api.statistiques(); } catch (e) { erreur = e.message; }
  }

  async function ouvrirAudit() {
    onglet = 'audit';
    try { audit = await api.audit(); } catch (e) { erreur = e.message; }
  }

  async function ouvrirSchema() {
    onglet = 'schema';
    try { schema = await api.schema(); } catch (e) { erreur = e.message; }
  }

  function chercherAutour(lon, lat) {
    filtreGeo = {
      libelle: `autour de ${lat.toFixed(3)}, ${lon.toFixed(3)} (${rayonKm} km)`,
      charger: () => api.autour(lon, lat, rayonKm),
    };
  }

  function chercherZone(bornes) {
    filtreGeo = {
      libelle: 'dans la zone visible',
      charger: () => api.zone(bornes),
    };
  }

  async function creerEspece() {
    erreur = '';
    const evolutions = STADES.map((niveau, i) => ({
      niveau,
      titre: `${nouvelle.nom} ${niveau}`,
      annees_xp: i * 3,
      salaire: String(30000 + i * 12000),
      attaques: [],
    }));
    try {
      await api.creer({
        numero: Number(nouvelle.numero),
        nom: nouvelle.nom,
        famille: nouvelle.famille,
        langages: nouvelle.langages.split(',').map((s) => s.trim()).filter(Boolean),
        evolutions,
        habitats: [],
      });
      creation = false;
      nouvelle = { numero: '', nom: '', famille: 'backend', langages: '' };
      await rafraichir();
    } catch (e) {
      erreur = e.message;
    }
  }

  async function restaurer(numero) {
    try { await api.restaurer(numero); await rafraichir(); }
    catch (e) { erreur = e.message; }
  }
</script>

<header>
  <h1>Pokedex des developpeurs</h1>
  <span class="sante" class:ok={sante?.mongo === 'ok'}>
    {#if sante?.mongo === 'ok'}
      MongoDB {sante.version} - {sante.especes} especes
    {:else}
      base hors ligne
    {/if}
  </span>
</header>

<nav>
  <button class:actif={onglet === 'catalogue'} onclick={() => (onglet = 'catalogue')}>Catalogue</button>
  <button class:actif={onglet === 'carte'} onclick={() => (onglet = 'carte')}>Carte</button>
  <button class:actif={onglet === 'statistiques'} onclick={ouvrirStats}>Statistiques</button>
  <button class:actif={onglet === 'audit'} onclick={ouvrirAudit}>Audit</button>
  <button class:actif={onglet === 'schema'} onclick={ouvrirSchema}>Schema</button>
</nav>

{#if erreur}
  <p class="bandeau">{erreur}</p>
{/if}

<main>
  <section>
    {#if onglet === 'catalogue' || onglet === 'carte'}
      <div class="filtres">
        <input placeholder="chercher un nom ou un langage" bind:value={recherche} />
        <select bind:value={famille}>
          <option value="">toutes les familles</option>
          {#each FAMILLES as f}<option value={f}>{f}</option>{/each}
        </select>
        <label><input type="checkbox" bind:checked={eteintes} /> especes eteintes</label>
        {#if onglet === 'carte'}
          <label class="rayon">rayon {rayonKm} km
            <input type="range" min="5" max="500" step="5" bind:value={rayonKm} />
          </label>
        {/if}
        <button onclick={() => (creation = !creation)}>Nouvelle espece</button>
      </div>

      {#if filtreGeo}
        <p class="filtre-geo">
          Filtre geographique : {filtreGeo.libelle}
          <button onclick={() => (filtreGeo = null)}>retirer</button>
        </p>
      {/if}

      {#if creation}
        <form class="creation" onsubmit={(e) => { e.preventDefault(); creerEspece(); }}>
          <input placeholder="numero" bind:value={nouvelle.numero} required />
          <input placeholder="nom" bind:value={nouvelle.nom} required />
          <select bind:value={nouvelle.famille}>
            {#each FAMILLES as f}<option value={f}>{f}</option>{/each}
          </select>
          <input placeholder="langages, separes par des virgules" bind:value={nouvelle.langages} />
          <button type="submit">Creer</button>
        </form>
      {/if}
    {/if}

    {#if onglet === 'carte'}
      <Carte {especes} {rayonKm} onRayon={chercherAutour} onZone={chercherZone} />
    {/if}

    {#if onglet === 'catalogue' || onglet === 'carte'}
      <p class="compte">{especes.length} espece{especes.length > 1 ? 's' : ''}</p>
      <div class="grille">
        {#each especes as espece (espece.numero)}
          <button class="carte-espece" class:eteinte={espece.eteinte_le}
                  onclick={() => (selection = espece.numero)}>
            <span class="numero">#{String(espece.numero).padStart(3, '0')}</span>
            <strong>{espece.nom}</strong>
            <span class="famille" style="background:{COULEURS[espece.famille] ?? '#666'}">
              {espece.famille}
            </span>
            <span class="stade">{STADES[espece.stade] ?? '?'}</span>
            <span class="titre">{espece.evolutions?.[espece.stade]?.titre ?? ''}</span>
            <span class="xp">xp {espece.xp ?? '-'}</span>
            {#if espece.eteinte_le}
              <span class="restaurer" role="button" tabindex="0"
                    onclick={(e) => { e.stopPropagation(); restaurer(espece.numero); }}
                    onkeydown={(e) => e.key === 'Enter' && restaurer(espece.numero)}>
                restaurer
              </span>
            {/if}
          </button>
        {/each}
      </div>
    {/if}

    {#if onglet === 'statistiques'}
      <table>
        <thead>
          <tr><th>famille</th><th>especes</th><th>xp total</th><th>sans xp</th>
              <th>habitats</th><th>salaire gourou moyen</th></tr>
        </thead>
        <tbody>
          {#each stats as ligne}
            <tr>
              <td><span class="famille" style="background:{COULEURS[ligne.famille]}">{ligne.famille}</span></td>
              <td>{ligne.nombre}</td>
              <td>{ligne.xp_total.toLocaleString('fr-FR')}</td>
              <td>{ligne.sans_xp}</td>
              <td>{ligne.habitats}</td>
              <td>{ligne.salaire_gourou_moyen?.toLocaleString('fr-FR')} EUR</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if onglet === 'audit'}
      <table>
        <thead><tr><th>champ</th><th>presence</th><th>types</th></tr></thead>
        <tbody>
          {#each audit as ligne}
            <tr>
              <td><code>{ligne.champ}</code></td>
              <td>
                <span class="jauge"><span style="width:{ligne.taux}%"></span></span>
                {ligne.taux} %
              </td>
              <td class:multi={ligne.types.length > 1}>{ligne.types.join(', ')}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}

    {#if onglet === 'schema'}
      <h2>Index</h2>
      <table>
        <thead><tr><th>nom</th><th>cles</th><th>options</th></tr></thead>
        <tbody>
          {#each schema?.index ?? [] as index}
            <tr>
              <td><code>{index.name}</code></td>
              <td><code>{JSON.stringify(index.key)}</code></td>
              <td>
                {index.unique ? 'unique ' : ''}
                {index.expireAfterSeconds ? `TTL ${index.expireAfterSeconds}s ` : ''}
                {index.partialFilterExpression ? 'partiel' : ''}
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <h2>Validation <small>({schema?.niveau} / {schema?.action})</small></h2>
      <pre>{JSON.stringify(schema?.validation ?? {}, null, 2)}</pre>
    {/if}
  </section>

  {#if selection != null && (onglet === 'catalogue' || onglet === 'carte')}
    <Fiche numero={selection} onchange={rafraichir} onfermer={() => (selection = null)} />
  {/if}
</main>

<style>
  header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.5rem .5rem;
  }
  header h1 { font-size: 1.3rem; }
  .sante {
    font-size: .85em;
    color: var(--alerte);
    border: 1px solid currentColor;
    border-radius: 999px;
    padding: 2px 10px;
  }
  .sante.ok { color: var(--accent); }

  nav { display: flex; gap: .4rem; padding: 0 1.5rem 1rem; }
  nav button.actif { border-color: var(--accent); color: var(--accent); }

  .bandeau {
    margin: 0 1.5rem 1rem;
    padding: .6rem 1rem;
    background: #fdeeee;
    border: 1px solid var(--alerte);
    border-radius: 6px;
    color: var(--alerte);
  }

  main {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
    padding: 0 1.5rem 2rem;
  }
  @media (min-width: 1000px) {
    main:has(> :global(aside)) { grid-template-columns: 1fr 360px; }
  }

  .filtres { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin-bottom: .8rem; }
  .filtres label { display: flex; align-items: center; gap: .3rem; color: var(--doux); }
  .rayon input { width: 140px; }
  .filtre-geo { color: var(--doux); display: flex; align-items: center; gap: .5rem; }
  .creation { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: .8rem; }
  .compte { color: var(--doux); margin: .5rem 0; }

  .grille {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: .6rem;
  }
  .carte-espece {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px .5rem;
    text-align: left;
    padding: .7rem .9rem;
    background: var(--carte);
  }
  .carte-espece.eteinte { opacity: .55; }
  .carte-espece.eteinte strong { text-decoration: line-through; }
  .carte-espece .numero { color: var(--doux); font-family: ui-monospace, monospace; }
  .carte-espece strong { font-weight: 600; }
  .carte-espece .stade, .carte-espece .titre, .carte-espece .xp {
    grid-column: 1 / -1; color: var(--doux); font-size: .85em;
  }
  .restaurer { grid-column: 1 / -1; color: var(--accent); font-size: .85em; text-decoration: underline; }

  .famille {
    display: inline-block; color: #fff; border-radius: 999px;
    padding: 0 8px; font-size: .78em;
  }

  .jauge {
    display: inline-block; width: 90px; height: 8px; background: var(--trait);
    border-radius: 4px; overflow: hidden; vertical-align: middle; margin-right: .4rem;
  }
  .jauge span { display: block; height: 100%; background: var(--accent); }
  .multi { color: var(--alerte); }

  pre {
    background: var(--carte); border: 1px solid var(--trait); border-radius: 8px;
    padding: 1rem; overflow-x: auto; font-size: .85em;
  }
</style>
