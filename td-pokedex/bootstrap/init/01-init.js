// Joue UNE SEULE FOIS, au premier demarrage, quand /data/db est vide.
// Pour le rejouer : docker compose down -v && docker compose up -d

db.createUser({
  user: "app",
  pwd: "app-password",
  roles: [
    // dbOwner = readWrite + dbAdmin. Le dbAdmin est indispensable au chapitre 09 :
    // la commande `collMod`, qui pose la validation JSON Schema, l'exige.
    { role: "dbOwner", db: "pokedex" },
    // La suite de tests travaille sur une base jetable, qu'elle cree et supprime.
    { role: "dbOwner", db: "pokedex_test" }
  ]
});

print("utilisateur applicatif 'app' cree sur pokedex et pokedex_test");
