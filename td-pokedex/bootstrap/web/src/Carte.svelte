<script>
  import { onMount, onDestroy } from 'svelte';
  import L from 'leaflet';
  import { COULEURS } from './api.js';

  let { especes = [], centre = [45.764, 4.8357], rayonKm = 50,
        onRayon = () => {}, onZone = () => {} } = $props();

  let conteneur;
  let carte;
  let cercle;
  let couche;

  onMount(() => {
    carte = L.map(conteneur).setView(centre, 6);

    // Tuiles OpenStreetMap. Si un proxy les bloque, la carte reste utilisable :
    // marqueurs et cercle s'affichent sur fond gris.
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(carte);

    couche = L.layerGroup().addTo(carte);

    // Leaflet prend [latitude, longitude] : l'inverse de GeoJSON.
    cercle = L.circle(centre, {
      radius: rayonKm * 1000,
      color: '#2f6f4f', weight: 2, fillOpacity: 0.08,
    }).addTo(carte);

    carte.on('click', (evenement) => {
      const { lat, lng } = evenement.latlng;
      cercle.setLatLng([lat, lng]);
      onRayon(lng, lat);            // vers l'API : longitude d'abord
    });

    dessiner();
  });

  onDestroy(() => carte?.remove());

  function dessiner() {
    if (!couche) return;
    couche.clearLayers();
    for (const espece of especes) {
      for (const habitat of espece.habitats ?? []) {
        const [lon, lat] = habitat.point.coordinates;   // GeoJSON : lon, lat
        L.circleMarker([lat, lon], {                    // Leaflet : lat, lon
          radius: 7,
          color: '#fff',
          weight: 2,
          fillColor: COULEURS[espece.famille] ?? '#666',
          fillOpacity: espece.eteinte_le ? 0.3 : 0.95,
        })
          .bindPopup(`<strong>#${String(espece.numero).padStart(3, '0')} ${espece.nom}</strong><br>${habitat.lieu}`)
          .addTo(couche);
      }
    }
  }

  $effect(() => {
    especes;
    dessiner();
  });

  $effect(() => {
    cercle?.setRadius(rayonKm * 1000);
  });

  export function bornes() {
    const b = carte.getBounds();
    return { ouest: b.getWest(), sud: b.getSouth(), est: b.getEast(), nord: b.getNorth() };
  }

  function chercherZone() {
    onZone(bornes());
  }
</script>

<div class="entete">
  <span class="aide">Cliquez sur la carte pour deplacer le cercle</span>
  <button onclick={chercherZone}>Chercher dans la zone visible</button>
</div>

<div class="carte" bind:this={conteneur}></div>

<style>
  .entete {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .5rem;
  }
  .aide { color: var(--doux); font-size: .9em; }
  .carte {
    height: 460px;
    border: 1px solid var(--trait);
    border-radius: 8px;
    background: #e8e6e1;
  }
</style>
