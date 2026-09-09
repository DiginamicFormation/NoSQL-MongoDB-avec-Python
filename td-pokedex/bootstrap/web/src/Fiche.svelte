<script>
  import { api, STADES, COULEURS } from './api.js';

  let { numero, onchange = () => {}, onfermer = () => {} } = $props();

  let fiche = $state(null);
  let erreur = $state('');
  let occupe = $state(false);

  $effect(() => {
    numero;
    charger();
  });

  async function charger() {
    erreur = '';
    try {
      fiche = await api.fiche(numero);
    } catch (e) {
      fiche = null;
      erreur = e.message;
    }
  }

  async function agir(action) {
    occupe = true;
    erreur = '';
    try {
      await action();
      await charger();
      onchange();
    } catch (e) {
      erreur = e.message;
    } finally {
      occupe = false;
    }
  }

  const evoluer = () => agir(() => api.evoluer(numero));
  const eteindre = () => agir(() => api.eteindre(numero));

  let auGourou = $derived(fiche && fiche.stade >= STADES.length - 1);
</script>

<aside>
  <div class="barre">
    <h2>Fiche</h2>
    <button onclick={onfermer}>Fermer</button>
  </div>

  {#if erreur}
    <p class="erreur">{erreur}</p>
  {/if}

  {#if fiche}
    <h3>
      <span class="numero">#{String(fiche.numero).padStart(3, '0')}</span>
      {fiche.nom}
    </h3>
    <span class="famille" style="background:{COULEURS[fiche.famille] ?? '#666'}">
      {fiche.famille}
    </span>

    <div class="chaine">
      {#each fiche.evolutions as evolution, i}
        <div class="stade" class:atteint={i <= fiche.stade} class:courant={i === fiche.stade}>
          <strong>{evolution.titre}</strong>
          <span class="niveau">{evolution.niveau}</span>
          <span class="salaire">{Number(evolution.salaire).toLocaleString('fr-FR')} EUR</span>
          <span class="attaques">{(evolution.attaques ?? []).join(' · ')}</span>
        </div>
      {/each}
    </div>

    <div class="actions">
      <button onclick={evoluer} disabled={occupe || auGourou}>
        {auGourou ? 'Deja gourou' : 'Faire evoluer'}
      </button>
      <button onclick={eteindre} disabled={occupe}>Eteindre</button>
    </div>

    <table>
      <tbody>
        <tr><th>langages</th><td>{(fiche.langages ?? []).join(', ') || '-'}</td></tr>
        <!-- xp ABSENT n'est pas xp a zero : on affiche un tiret. -->
        <tr><th>xp</th><td>{fiche.xp ?? '-'}</td></tr>
        <tr><th>habitats</th><td>{(fiche.habitats ?? []).map((h) => h.lieu).join(', ') || '-'}</td></tr>
        <tr><th>schema</th><td>v{fiche.schema_version}</td></tr>
      </tbody>
    </table>

    {#if Object.keys(fiche.specifique ?? {}).length}
      <h3 class="sous-titre">Particularites de la famille</h3>
      <table>
        <tbody>
          {#each Object.entries(fiche.specifique) as [cle, valeur]}
            <tr>
              <th>{cle}</th>
              <td>{Array.isArray(valeur) ? valeur.join(', ') : String(valeur)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</aside>

<style>
  aside {
    background: var(--carte);
    border: 1px solid var(--trait);
    border-radius: 8px;
    padding: 1rem;
  }
  .barre { display: flex; justify-content: space-between; align-items: center; }
  .numero { color: var(--doux); font-family: ui-monospace, monospace; }
  .famille {
    display: inline-block;
    color: #fff;
    border-radius: 999px;
    padding: 1px 10px;
    font-size: .82em;
  }
  .chaine { margin: 1rem 0; display: grid; gap: 4px; }
  .stade {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 0 .6rem;
    padding: 6px 10px;
    border: 1px solid var(--trait);
    border-radius: 6px;
    opacity: .45;
  }
  .stade.atteint { opacity: 1; }
  .stade.courant { border-color: var(--accent); background: #f0f6f2; }
  .niveau { color: var(--doux); font-size: .85em; text-align: right; }
  .salaire { color: var(--doux); font-size: .85em; }
  .attaques { grid-column: 1 / -1; color: var(--doux); font-size: .82em; }
  .actions { display: flex; gap: .5rem; margin-bottom: 1rem; }
  .sous-titre { margin-top: 1rem; color: var(--doux); font-size: .9em; }
  .erreur { color: var(--alerte); }
</style>
