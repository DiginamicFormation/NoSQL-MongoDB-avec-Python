// Joué UNE SEULE FOIS, au premier démarrage, quand /data/db est vide.
// Pour le rejouer : docker compose down -v && docker compose up -d

db.createUser({
  user: "app",
  pwd: "app-password",
  roles: [{ role: "readWrite", db: "boutique" }]
});

print("utilisateur applicatif 'app' créé sur la base boutique");
