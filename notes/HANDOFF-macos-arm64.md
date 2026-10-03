# Handoff — Forbidden Memories sur macOS Apple Silicon

État vérifié le 3 octobre 2026. Ce document est le point de reprise opérationnel ; les deux autres notes macOS conservent l’historique des investigations.

## Intégration durable et rebase upstream — 3 octobre 2026

La branche de travail est `integration/macos-arm64`. Elle est rebasée sur
`origin/master` à `8f27718bad44302c6b3f74cdfaa43c0525b973f0`, après la release
`v0.2.0` (`0185f58df`). Le spike `spike/macos-arm64` reste à
`a42660450fa558bb7ebb0a194b072a1672e6fc8e`. Les branches
`backup/macos-arm64-before-upstream-20261003` et
`backup/macos-arm64-wip-20261003` conservent respectivement le spike et le travail
d'intégration avant rebase. Le commit d'intégration est explicitement WIP :
la migration vers le build commun et la passe LLVM n'est pas achevée.

Les conflits ont été résolus en conservant les corrections upstream 64 bits,
les listes de parties des modèles lues par variadiques/stack guest, et les
annotations G32 nouvelles. La configuration partagée inclut désormais le module
`credits` et sa sélection par la porte native vérifiant les données retail.
Le nouveau contrôle réseau reçoit une variante Darwin utilisant `accept` et
`fcntl(FD_CLOEXEC)` ; Linux et Windows conservent leurs chemins existants.

Validation après rebase : `make basic-types check-g32` passe (604 sources C).
Les 104 fichiers console/header modifiés produisent les mêmes tokens prétraités
que le dernier upstream avec la cible MIPS ; ce contrôle ne constitue pas un
matching binaire. Les 17 scénarios de `test_native.py` passent, ainsi que leur
exécution ASan/UBSan. Les tests upstream `control_protocol` et `control_net`
passent sur macOS (le test loopback exige de sortir du sandbox). La compilation
des 748 unités ARM64 passe avec `build_arm64.py --compile-only` ; le linkage
et les parcours de jeu du build structuré restent à valider. Les preuves de gameplay des sections historiques concernent
le spike : elles doivent être repassées sur le nouveau binaire d'intégration.
Les journaux du rebase sont sous `tmp/arm64-integration/rebase-*`.

## Entrée commune et lanceurs — 3 octobre 2026

La CI construit maintenant les trois jeux complets sans disque et ajoute un
job macOS ARM64 (`macos-15`) avec LLVM 21.1.8, cache des dépendances vérifiées,
tests LLVM, linkage/polices, composants normaux et ASan/UBSan. Les premiers
jobs ont révélé des tests à adapter après extraction des sous-systèmes d'état
et un `tmpfile()` non portable sur Windows ; leur correction est validée
localement, les résultats Linux/Windows complets restent attendus.

`test_llvm_guest.py` comporte 12 tests. Un fixture IR transformé puis compilé
et exécuté en optimisation vérifie les accès PS1, conversions, memcpy/memmove/
memset, atomiques et callback sur des régions contrôlées. Les rejets couvrent
les espaces d'adresse non supportés, l'assembleur machine, les types scalable,
les appels avec unwind et les adresses PS1 hors 32 bits. Preuve locale :
`llvm-execution-tests.log`.

`tools/pc/build.py --target linux|windows|macos` est l'entrée commune. Les
métadonnées de cibles, sources résidentes, modules et sélection native sont
partagées dans `build_config.py` ; les drivers n'analysent pas le Python de
l'autre cible. Les compilateurs i386/i686 existants restent sélectionnés par
le driver 32 bits, ARM64 par son driver structuré. La cible macOS commune
produit `tmp/pc/macos/memories-arm64`.

`play.sh` détecte Darwin, vérifie Python/xcrun et construit/lance le jeu via
`build-pc.sh`. Ce dernier gère run/trace/load sur macOS ; sa construction
Linux/Windows conserve ses deux builds et le contrôle de layouts. `play.bat`
passe aussi par l'entrée commune, avec son répertoire game32 Windows conservé.
CMake expose `pc_game` et `MEMORIES_GAME_TARGET` (défaut selon la plateforme).
Preuves : `common-macos-build.log`, `common-play.log` et `common-play.ppm`,
`common-cmake-game.log`. Les composants passent avec Clang 21.1.8 en normal
(`common-native-llvm21.log`). Sur l'hôte macOS 26, le runtime ASan officiel
21.1.8 se bloque avant `main` : l'initialisation de la shadow memory parcourt
le cache dyld Swift, dont l'allocation réentre dans l'initialisation ASan.
La trace est dans `llvm21-asan-sample.txt`. Cela ne valide pas cette suite avec
LLVM 21 ; la CI macOS 15 doit encore la vérifier sur son propre système.
Les 21 scénarios ASan/UBSan passent avec Xcode
(`common-native-xcode-sanitize.log`), sans mélanger les runtimes.

## Dépendances locales : preuves

`tools/pc/macos_deps.py` prépare SDL3 3.4.16, FreeType 2.14.3, libpng 1.6.58,
zlib 1.3.2 et zstd 1.5.7 sous `tmp/pc/macos-deps`. Les archives sont verrouillées
par SHA-256 ; CMake 4.4.3 et Ninja 1.13.2 sont aussi pris dans leurs releases
macOS officielles vérifiées. La compilation utilise Clang/LLVM 21.1.8 et le
SDK renvoyé par `xcrun --sdk macosx --show-sdk-path`. La découverte CMake des
bibliothèques est limitée au préfixe local et au SDK, sans package manager.

Le jeu lie les archives locales explicitement. La dépendance absolue zstd
encodée dans llvm-config par la machine de build officielle est remplacée par
l'archive locale ; toute autre dépendance absolue extérieure est refusée.
Les quatre consommateurs de polices macOS passent par CoreText pour découvrir
les fichiers système, puis par FreeType pour les dessiner. Linux/fontconfig et
Windows conservent leurs branches. `test_macos_linkage.py` vérifie les vraies
architectures des archives, les dépendances Mach-O du jeu/compilateur et le
chargement/raster des polices UI, gras, serif et japonais. Les tests CMake de
polices et titres de cartes passent ; le test des polices passe sous sanitizers.

Preuves : build complet et quatorze parcours gameplay sous
`tmp/arm64-integration/macos-local-*`, linkage/fonts sous `macos-linkage.log`,
CTest sous `macos-font-ctest-final.log`. Build depuis l'index exporté (arbre
`34d660c19ecee79f1e0e36a02009468cc3a9b2bd`) dans
`/Users/vincentmetton/Code/FM/macos-clean-build-20261003` : seules les archives
et le cache LLVM officiel sont réutilisés, aucun objet/source générée du spike.
Les dépendances et 754 unités du jeu sont reconstruites avec un PATH système.
Logs de cette preuve : `macos-clean-build.log`, `macos-clean-linkage.log`,
`macos-clean-victory.log`.

La victoire française avec reprise d'état passe et son chunk `language`
confirme réellement `fr` (`macos-local-french-victory.log`). Les deux rapports
de progression française restent à reproduire séparément.

## Save states natifs intégrés — 3 octobre 2026

Revalidation du 4 octobre sur `tmp/pc/macos/memories-arm64`, produit par
l'entrée commune : reprise du deck dans un processus neuf avec pixels
identiques, F5/F7 SDL dummy, trois rechargements via contrôle, RAM identique,
refus des états incompatibles sans mutation et autosaves réussis. Journaux :
`common-save-states.log` et `common-state-control.log`.

La demande explicite de save states remplace leur exclusion initiale. Le backend
ARM64 est maintenant raccordé aux commandes F5/F7, aux slots, aux autosaves et au
canal de contrôle. Les sauvegardes normales restent distinctes. Détails,
commandes et limites : [macos-arm64-save-states.md](macos-arm64-save-states.md).

Le build structuré compile et lie `tmp/arm64-build/memories-arm64` (753 unités).
La pile de jeu dédiée est protégée par deux pages de garde. VSync capture les
registres ARM64 ; le chargement restaure depuis la pile de service. Les contextes
setjmp sont capturés par le même mécanisme et font partie de l'état. Les régions
conservent leurs tokens PS1, identités de globals et ownership des allocations.
Les pointeurs hôtes sont relocalisés pour ASLR ; les champs des serializers sont
traités séparément pour respecter les callbacks non alignés dans leurs chunks.
Les mappings guest, dont la pile MIPS 0x9ff00000 utilisée par les modèles 3D,
sont recréés avec leur payload ; stack_top/current_sp de l'interpréteur sont
restaurés avec eux.

Les serializers, contrôles des mods et de la langue sont partagés avec i386.
Le fichier ARM64 a une version distincte, un UUID d'exécutable et une empreinte
d'intégrité. Un autre exécutable, des données incompatibles, un fichier tronqué
ou corrompu sont refusés avant mutation. Il n'y a pas de conversion d'états
i386/émulateur ni de garantie de transport entre deux builds ARM64. Conserver
les sauvegardes normales pour cela.

Preuves de restauration : `test_arm64_states.py` reprend un état du deck dans un
nouveau processus, reproduit les données de duel/deck et les pixels, puis teste
F5 et trois F7 via SDL dummy. `test_arm64_state_control.py` vérifie trois reprises,
la RAM du jeu, les refus sans mutation et les autosaves tournantes. Le bloc audio
retail à 0x801e0000 continue avec l'horloge hôte : le test de RAM rejouée couvre
l'image du jeu jusqu'à cette frontière et ne revendique pas des samples identiques.
`test_arm64_gameplay.py --state-frame` permet aussi une reprise pendant les
mécaniques du duel. Fusion et équipement à frame 9000 ont des pixels identiques.
Le combat 3D sauvegardé à frame 20000, dans le mode c1, reprend dans un nouveau
processus et revient au terrain avec les mêmes dégâts et pixels finaux.

Les 21 scénarios de composants passent en normal et ASan/UBSan ; les frontières
assembleur de changement de pile sont exécutées séparément sans annotations de
pile des sanitizers. Les six tests LLVM et `make basic-types check-g32` passent.
Journaux : `tmp/arm64-integration/state-*`. Aucun test de cadence ni fenêtre réelle.
Les quatorze parcours gameplay et les sauvegardes normales/deck pad et SDL
repassent avec le backend natif de save states.

La migration globale reste en cours : CI et validation
Linux/Windows/matching console restent
à terminer. Les exclusions de save states mentionnées plus bas sont historiques.

Les runners gameplay et sauvegarde acceptent maintenant `--binary` pour tester
explicitement le nouveau build. Le runner gameplay accepte `--language` et
isole chaque exécution dans un répertoire neuf. Les sauvegardes normales,
chargement dans un nouveau processus, et deck retail/slots/clavier SDL passent.
Le parcours victoire lancé avec `--language 2` atteint récompense et dialogue
(ce contrôle ne prouve pas encore le retour au terrain de duel ou la fin des
villageois rapportés par l'utilisateur). Les tests natifs passent 19 scénarios,
y compris sous ASan/UBSan. Journaux : `tmp/arm64-integration/structured-*` et
`state-foundations-*`. Aucun test de cadence ni fenêtre réelle.

## Objectif et consignes de travail

Faire fonctionner Forbidden Memories sur le MacBook Air M3 de l’utilisateur : lancement natif ARM64, jeu réellement jouable, sauvegarde et chargement. Le build et un duel complet jusqu'à la défaite et au game over sont validés. La sauvegarde dans la boutique et le chargement dans un nouveau processus sont validés. Les essais manuels de fenêtre/audio sont laissés à l’utilisateur conformément à sa consigne. Voir la mise à jour de reprise ci-dessous avant les sections historiques.

L’utilisateur autorise les changements de code, builds et tests. Il souhaite être sollicité uniquement pour les décisions architecturales et les blocages importants. Il a explicitement approuvé un prototype limité de traduction des adresses PS1 vers la mémoire native et de résolution des callbacks, sans modifier les sources originales du jeu ni les chemins Linux/Windows. **Dernière consigne : ne pas mesurer la cadence en fenêtre réelle ; privilégier les subtilités du jeu (fusion, équipements, etc.). L’utilisateur prend en charge les essais manuels.** Aucun agent supplémentaire n’a été lancé pendant cette reprise.

## Mise à jour de reprise — 2 octobre 2026

### Reprise du 3 octobre : animations de combat

Deux rapports manuels supplémentaires sont apparus : `tmp/pc/crash-73282.txt` (2 octobre, GTE store à l'adresse concaténée `0x9ff3ff789ff3ff7c`) et `tmp/pc/crash-80709.txt` (3 octobre, appel à `0x8006af748006cd78`). Le second identifie la copie des quatre callbacks de `D_800114E8` dans le tableau local `handlers` de `func_8004EB00`, dans `model_intro_controller.c`. La copie retail est de 16 octets, mais le tableau local était natif 4×8 octets. L'override généré ajoute `G32` à ses entrées. `test_model_effect_guest_callbacks.py` exécute la vraie fonction traduite dans ses états 6 et 23 : premier et dernier handlers, argument et état préservés. Normal et ASan/UBSan passent. La variante non corrigée reproduit un SIGSEGV (`tmp/model-effect-guest-callbacks/negative.log`). Le build à 737 unités passe. Cela corrige la cause du rapport 80709 ; le rapport GTE 73282 est expliqué et reproduit par le diagnostic ci-dessous.

Le crash GTE a maintenant été reproduit par de vraies entrées de manette : mod de deck normal avec les cartes 75 et 347, sort, tour CPU, invocation puis attaque avec défenseur. `tmp/arm64-gameplay/attack-83250/run.log` donne la pile LLDB : `RotAverage4` → `call_native` → module MODEL → `Main_RunAnimatedBattle`. Le pont de `mips.c` invoquait toutes les fonctions comme douze `uint32_t`. Sur ARM64, les neuvième et dixième pointeurs de `RotAverage4` sont deux arguments de huit octets dans la pile ; ils recevaient donc chacun deux mots PS1 concaténés. Ce défaut est corrigé par les wrappers typés générés depuis les prototypes IR dans `native_call_marshalling.py`. Le chemin i386 reste inchangé. Les pointeurs de retour natifs sont encodés en tokens guest ; les longs SDK et couleurs de quatre octets sont traités explicitement. Les nouveaux paramètres larges et fonctions variadiques non audités font échouer le build.

Preuve après correction : `tmp/arm64-gameplay/attack-87149/run.log`, sortie 0, entrée en mode c1, animation 3D puis retour c3 au terrain jusqu'à frame 32000, LP joueur/adversaire 7700/6500. Le scénario durable est maintenant `test_arm64_gameplay.py --case animated-battle` (neuvième cas). Il impose le passage par c1 puis le retour au duel et les dégâts ; une simple capture ne suffit pas. Aucun état mémoire n'est injecté.

Un autre accès à la pile o32 était présent dans `Model_QueueTintRequestForParts` : parcours des arguments au-dessus du paramètre `a4`. L'override généré utilise `va_list` sur ARM64. `test_model_tint_variadic.py` exécute cette vraie fonction avec trois indices de pièces et une liste vide, vérifie le masque et les couleurs. Normal et ASan/UBSan passent. `test_native_call_marshalling.py` vérifie dix pointeurs, douze arguments de tailles mixtes, retour pointeur, couleurs, petits entiers signés et longs signés/non signés ; normal et ASan/UBSan passent. Les 17 tests natifs repassent. Les neuf parcours d’intégration passent ensemble sur le build final (`tmp/arm64-build/gameplay-native-calls.log`), dont le combat 3D. Les originaux `src/game` et `src/overlays` sont inchangés.

### Reprise suivante : pièges et rituel en duel

Les deux scénarios de piège sont maintenant couverts par les vraies entrées de manette. `--case trap` pose Widespread Ruin, passe le tour et laisse l’IA attaquer : disparition du piège et de l’attaquant, compteur 1, LP joueur 8000, puis nouvelle main. `--case trap-threshold` pose House of Adhesive Tape face à un deck CPU de Man-eating Plant (800 ATK) : piège conservé, compteur 0, LP joueur 7200. Les deux passent. Il faut arrêter les confirmations après la pose du piège : sélectionner de nouveau la carte sur le terrain la consomme avant l’attaque, ce qui expliquait le premier replay insuffisant.

Le rituel est reproduit sans injection RAM : fixture de starter (30 Blue-Eyes et 10 rituels 670), recette normale de mod `[1,1,1] → 364`, deck CPU fixe de carte 75. Après trois poses dans des colonnes distinctes, les trois Blue-Eyes sont consommés et Black Luster Soldier 364 est publié au terrain, 3000 ATK / 2500 DEF, puis retour à la phase 8005. Preuve : `tmp/arm64-gameplay/ritual-89130/run.log`, sortie 0 à frame 29000. Les cas durables `ritual` et `ritual-failure` passent : présence de trois records de sacrifices distincts, résultat unique 364 et consommation de la carte rituelle ; refus avec un seul sacrifice en le conservant. Les treize parcours ont passé ensemble (`tmp/arm64-build/ritual-trap-gameplay-all.log`). La recette de ce premier replay est une recette de mod ; la recette retail est désormais validée par le parcours décrit ci-dessous. Le refus doit consommer le rituel en laissant le seul sacrifice présent intact.

Les diagnostics optionnels de `state_translated.c` montrent désormais les deux zones arrière et les monstres adverses. La main était incorrectement décodée après plusieurs tours : `DuelSideState.hand` contient des indices de deck et non des indices de records du terrain. Le diagnostic lit maintenant les records via `D_800907CC`, avec le slot sélectionné à l’offset 0x0e du curseur. Les treize parcours repassent avec cette trace corrigée ; les 17 tests natifs et les composants rituel/règles ASan/UBSan passent. Aucun changement des règles du jeu ni des sources originales n’a été nécessaire pour ces parcours.

Le menu Build Deck autonome a aussi été parcouru après un vrai LOAD de sauvegarde, via les deux déplacements Down de son menu secondaire : mode c7, sept tris dans chacun des deux panneaux, retour c8. Les variantes avec `MEMORIES_DECK_SLOTS=0` et avec le sélecteur PC activé passent (`tmp/arm64-gameplay/deck-standalone-89677/run.log`, `deck-standalone-89837/run.log`). Le sélecteur PC accepte les mêmes entrées de manette : il faut lui confirmer le slot avec Cross avant d’entrer dans la grille. `test_arm64_save_load.py` couvre maintenant SAVE, LOAD et les deux variantes du menu autonome dans des processus neufs, sans changer la sauvegarde pendant les tris. Le runner complet passe : `tmp/arm64-build/ritual-trap-save-load.log`, artefacts sous `tmp/arm64-save-load/run-89921/`.

**Retour manuel du 3 octobre :** l'utilisateur indique désormais que le gel lors du changement d'onglet/tri ne s'est pas reproduit. Les tests ne permettent pas d'attribuer une cause certaine à cet incident initial. `deck-editor` passe les sept tris des deux panneaux, retire puis remet la carte 24, ouvre/ferme sa fiche, utilise L1/R1/L2/R2 puis entre en duel. Les maintiens de Start/Select et flèches combinées passent aussi (`tmp/arm64-gameplay/deck-repeat-87873/run.log`). Ne pas assimiler une absence de reproduction à une correction identifiée.

Le parcours clavier SDL complète ces essais : pilote `dummy`, renderer `software`, aucune fenêtre OS, événements keydown/keyup de X, flèches, Enter et S. Depuis un vrai LOAD, il confirme le slot PC, parcourt les deux panneaux et leurs sept tris, puis revient en mode c8 avec 40 cartes. Preuve initiale : `tmp/arm64-gameplay/deck-keyboard-90777/run.log`, sortie 0. Le parcours est intégré à `test_arm64_save_load.py` ; les autres variantes restent headless par manette. Ce test ne mesure aucune cadence.

Le runner complet avec ses cinq processus neufs passe : SAVE, LOAD, Build Deck retail, Build Deck avec sélecteur PC, puis Build Deck au clavier SDL. Log `tmp/arm64-build/save-load-keyboard.log`, artefacts `tmp/arm64-save-load/run-90872/`. Les trois variantes parcourent les sept tris des deux panneaux et reviennent c8 ; le fichier de sauvegarde reste inchangé.

Le quatorzième scénario `--case ritual-retail` lit d'abord la recette 670 du disque utilisateur dans les sept tables de terrain : `[27,38,58] → 364`. Aucun override de recette dans le mod ; seuls les starters et le deck CPU sont contrôlés par le mécanisme normal des mods. Trois sacrifices distincts sur le terrain, puis le vrai rituel 670 : résultat unique Black Luster Soldier 364, 3000 ATK / 2500 DEF, disparition des trois sacrifices et de la carte rituelle, retour phase 8005, LP 8000/8000. `tmp/arm64-build/ritual-retail-gameplay.log` passe. Les treize autres parcours ont passé ensemble sur le même build. Chaque scénario rejette maintenant les diagnostics de fallback (« cannot run », « native stand-in », « unimplemented game routine ») ; aucun n'est présent dans leurs logs.

Le build actuel compile et lie 737 unités. Le conflit de déclarations des fonctions du bridge des effets du duel a été corrigé dans `build_arm64.py` : les cinq fonctions déjà déclarées avec leur vrai prototype ne reçoivent plus une déclaration générique `void(void)`.

Les adaptations de copies générées dans `guest_pointer_overrides.py` corrigent les grilles d'affichage, les pointeurs et le pool d'étincelles de Free Duel, les listes et canaux HMD, le stockage de callbacks du modèle, les pointeurs de la carte de campagne, les streams des textes du duel, la reconstruction des cartes, le pointeur des données de rituel et les curseurs de combat/terrain. Les valeurs de fin de liste HMD `0xffffffff` sont comparées sous leur forme guest zéro-étendue. Le SDK PC `GsLinkAnim` écrit maintenant des entrées `G32`. Les sources originales du jeu restent inchangées.

Deux corrections structurantes :

- `GuestRuntime_EncodePointer` privilégie toutes les régions qui **contiennent** l'adresse avant d'accepter une adresse juste après une région. Deux globals natifs contigus, dont les tokens guest sont alignés séparément, étaient confondus. Le workspace Build Deck était décalé de deux octets et empêchait l'entrée en duel. La même correction protège la frontière RAM/scratchpad, tout en conservant les vrais pointeurs de fin de tableau.
- Le handler local d'`AiScript_Run` utilise `AiScriptHandler G32` pour comparer les callbacks chargés depuis la table aux terminaux de script. La comparaison guest/natif échouait et l'IA continuait après la fin du script jusqu'à un callback nul.

Preuves d'intégration :

- Saisie du nom, séquences de campagne, menu du deck et entrée en duel.
- Sélection de plusieurs cartes, fusion refusée et fusion retail 75 + 202 → 487 (Flower Wolf), avec 1 800 ATK / 1 400 DEF et compteur de fusion incrémenté.
- Man-eating Plant + Megamorph dans un deck de test via le mécanisme normal des mods : carte 75, stats de base 800/600, modificateur +1 000, compteur d'équipement incrémenté.
- Tremendous Fire : animation complète, une carte consommée, compteur de magie incrémenté, LP adverses 8 000 → 7 000.
- Combats, changement de tours, fusions de l'IA et effets de terrain. Un parcours contrôlé de sorts a atteint LP joueur 0 / adversaire 3 000, phases de résultat `800c`/`800d`, script de défaite (scène 97), puis game over (mode 12). Les confirmations aveugles suivantes relançaient une nouvelle partie et sa carte : ce retour ne doit pas être confondu avec une continuation de la campagne perdue. Le parcours stock de seize tours s'arrêtait sur une cible d'équipement vide : ce n'était pas un plantage, mais une limite des entrées aveugles du script.

Tests reproductibles : `python3 tools/pc/test_arm64_gameplay.py` (disque local requis, quatorze scénarios, aucune fenêtre, sauvegardes et pixels uniquement sous `tmp/arm64-gameplay`). Les assertions vérifient le retour au terrain, les cartes produites, leurs stats, les compteurs et les LP ; les deux scénarios `deck-editor` parcourent les tris et commandes du deck avant duel et depuis Free Duel. Les captures sont des pixels du disque local, à ne pas versionner.

Nouveaux runners sans disque (IR du build requis) : `test_display_grid_guest_storage.py`, `test_model_rows_guest_storage.py`, `test_campaign_map_guest_storage.py`, `test_duel_text_guest_storage.py`, `test_ai_vm_guest_callbacks.py`, `test_duel_card_guest_storage.py`, `test_duel_rules_guest.py`, `test_duel_ritual_guest_storage.py`, `test_free_duel_guest_storage.py`. Ils exercent les fonctions réellement traduites, avec sentinelles adjacentes, règles de sacrifices distincts et seuils des pièges. Les exécutions normales et ASan/UBSan passent. Les tests natifs (17 scénarios), IR, overrides, bridges, stockage sonore, rendu, menus et `libmcrd` passent aussi. `basic-types`, `check-g32`, `git diff --check` passent.

Autres preuves finales :

- Victoire contrôlée via un mod de test qui démarre l'adversaire à 1 000 LP : Tremendous Fire fait passer ses LP à zéro, le jeu termine le résultat, ajoute une carte au coffre et cinq starchips, puis charge le dialogue de victoire de Simon (scène 96). Aucun état mémoire n'est injecté pour produire la victoire.
- Free Duel : le déplacement du curseur révélait un pointeur contenant le mot de flags voisin (`0x40800f184a`). Les trois globals `gFreeDuel_pThumbWidget`, `gFreeDuel_apSparklePool`, `gFreeDuel_pCursorWidget` et les curseurs de pool sont maintenant `G32` dans les copies générées. Le scénario parcourt la grille 5 × 8, sélectionne Duel Master K et arrive au choix d'étoile gardienne du duel.
- Sauvegarde normale : depuis le premier écran de carte, Down vers le Duel Ground, Right vers Town Plaza, Right vers Card Shop (location 13 / scène 45). Save écrit `saves/slot01.sav`, 8 192 octets, header SC, deux copies identiques de l'état, quarante cartes et scène 45. `python3 tools/pc/test_arm64_save_load.py` repart ensuite d'un nouveau processus, choisit LOAD puis le slot et Campaign, restaure scène 45 et deck de 40 cartes, et vérifie que le chargement ne modifie pas le fichier. Chaque exécution crée un répertoire utilisateur unique sous `tmp/arm64-save-load`.

Les huit scénarios ont passé ensemble sur le build recompilé à 17:36 (`tmp/arm64-build/gameplay-deck-regression.log`). Les deux scénarios Build Deck ont ensuite repassé avec Select et Start pour vérifier les tris dans les deux sens. Les 17 tests natifs ont repassé. `test_native.py` inclut désormais aussi le test de délégation VSync et de rejet explicite des save states, pour éviter qu'un diagnostic du gameplay rende ce test impossible à lier. L'essai headless avec timer normal (`tmp/arm64-gameplay/deck-sort-timer`) avance en campagne mais suit un autre parcours avec les confirmations à frames fixes : ce n'est pas une reproduction validée de Build Deck ni une preuve de blocage.

Lancement manuel du build actuel, depuis n'importe quel dossier :

```sh
python3 /Users/vincentmetton/Code/FM/new-port/tools/pc/run_arm64.py
```

Cela utilise le disque local et le répertoire de test `tmp/arm64-build/user`. Le lanceur n'emploie pas les saves du joueur. Aucune campagne complète n’est revendiquée. Le rituel et les pièges sont désormais exercés dans des duels headless par manette ; leurs règles sont aussi vérifiées par les fonctions réellement traduites et les tests de sentinelles. Les save states restent non supportés, distinctement des sauvegardes normales qui sont fonctionnelles.

`MEMORIES_TRACE_GAMEPLAY=1` active les diagnostics de mode/scène toutes les 120 frames, états du deck, phases du duel, LP, compteurs, main et cartes du terrain. Le champ location est brut et n'est pertinent que lorsque l'overlay de carte est actif. La cadence des runs accélérés ne constitue pas une mesure en fenêtre réelle.

Les sections suivantes décrivent le handoff précédent et certaines limites ont depuis été levées. Garder les artefacts `tmp/arm64-build/` et `tmp/arm64-gameplay/`.

- Repo actif : `/Users/vincentmetton/Code/FM/new-port`.
- Branche : `spike/macos-arm64` ; HEAD : `496dd953620302cdcf234f176cde53afdf103614`.
- Aucun commit ni push effectué pendant ces travaux. Beaucoup de fichiers nouveaux sont encore non suivis : ne pas les perdre lors d’un nettoyage.
- `src/game` et `src/overlays` originaux sont inchangés, vérifié par Git. Les adaptations du jeu sont appliquées aux copies générées ou à l’IR LLVM.
- `old-reference` n’a pas été modifié. Le `.DS_Store` non suivi était préexistant.
- Lire `.github/copilot-instructions.md` avant de reprendre. Exécuter les commandes depuis la racine de `new-port` ; mettre les fichiers temporaires dans `tmp`.
- Pour une question de documentation propre à une bibliothèque/API, suivre les instructions Context7 de l’utilisateur : résolution `ctx7 library`, puis `ctx7 docs`, hors sandbox. Pas nécessaire pour le diagnostic de logique ou de layout mémoire.

## Architecture retenue

Le Mach-O ARM64 standard ne permet pas de reproduire les mappings bas fixes de la PS1. Les tentatives de libérer PAGEZERO et mapper ces adresses échouent ; les variantes à PAGEZERO réduit étaient tuées par macOS. Le backend expérimental conserve donc les **valeurs/adresses PS1 sur 32 bits**, mais traduit les accès vers des allocations natives hautes. Les callbacks natifs conservent leur adresse complète sur 64 bits.

Le pipeline compile le C en IR non optimisé, traduit les accès mémoire/callbacks, puis optimise l’IR traduit. Les pointeurs stockés dans les structures PS1 utilisent `G32` ; les anciens `long` du SDK PS1 utilisent `PSXLONG`. Un remplacement global de tous les pointeurs doubles serait incorrect : certains désignent des tableaux locaux natifs. Chaque adaptation est donc bornée et testée.

Fichiers centraux :

- `tools/pc/build_arm64.py` : build natif de 737 unités, génération des tables et bridges ; optimisation activée par défaut.
- `tools/pc/translate_guest_ir.py` : traduction des accès, casts, callbacks, intrinsics et constantes de pointeurs.
- `tools/pc/guest_pointer_overrides.py` : corrections précises des copies générées du jeu.
- `src/pc/guest/translated_runtime.[ch]` : résolution mémoire/fonctions, encodage des tokens, aliases et régions natives.
- `src/pc/guest/translated_image*` : chargement du disque/exécutable et backend de résolution des modules.
- `translated_alloc.c`, `translated_mman.c`, `translated_jmp.c`, `translated_setjmp_arm64.S`, `translated_libc.c` : adaptation des services natifs.
- `src/pc/guest/state_translated.c` : entrée et boucle natives ; les save states d’émulateur restent explicitement non supportés.
- `tools/pc/direct_overlay_bridges.py` : imports directs typés vers le module effectivement chargé ou le gate existant.

Les collisions entre noms retail et libc native ont été corrigées, notamment `open`, `exit` et `memchr` créé par l’optimiseur. Ne pas réintroduire de stub retail sous un nom libc ordinaire. Les callbacks stockés par des expressions constantes `ptrtoint` sont encodés à l’exécution ; les initialisateurs statiques non pris en charge sont rejetés.

## Ce qui fonctionne et preuves

Le disque utilisateur USA `SLUS_014.11` est chargé réellement : exécutable de 1 902 592 octets, entrée `0x800129d8`. Le fichier propriétaire est ignoré sous `game/YGOFM Vanilla (Base).bin` ; ne pas le suivre dans Git.

Le jeu a été lancé dans une vraie fenêtre Cocoa sur le M3, avec SDL3 3.4.16 ARM64 et CoreAudio. Le titre et le menu `NEW GAME / LOAD / 2P DUEL / TRADE / OPTION` s’affichent et répondent à Start. Le clavier du nom s’affiche, écrit le caractère A dans le buffer PS1 `0x801d060c`, termine l’animation du glyphe et quitte correctement après END et les pages du message de code du duelliste.

### Performances

Le menu tournait auparavant autour de 22 FPS. Le profil montrait presque tout le coût dans la résolution des accès mémoire du rasteriseur logiciel. `tools/pc/host_renderer_boundaries.py` compile désormais SoftGpu comme composant natif optimisé et résout ses neuf frontières de pointeurs une fois par appel. Le SDK et le jeu restent traduits.

Mesures en fenêtre réelle : rendu environ 1,1 ms, traitement jeu 2,1 ms, présentation 2,9 ms. Fenêtres consécutives de 120 frames : 59,91 et 59,96 FPS, aucun VBlank manqué. La saisie du nom rapporte aussi environ 60 FPS sans VBlank manqué. Les phases vidéo/intro rapportent encore environ 15 FPS ; leur cause et leur cadence attendue ne sont pas établies. Ne pas annoncer 60 FPS dans toutes les scènes.

Le rendu natif et le rendu entièrement instrumenté produisent le même hash VRAM `d31a62f999bbd9db` après 512 commandes variées. Tests de clipping, CLUT, transfert, blend et widescreen validés normalement et avec ASan/UBSan. L’option `--instrument-softgpu` permet une comparaison avec l’ancien chemin.

Un dump PPM à la frame de sortie 820 a présenté des bandes alors que les captures de la fenêtre réelle et les captures ultérieures étaient correctes. Le dump intervient avant la présentation. Ce problème de capture reste documenté ; ne pas le présenter comme définitivement expliqué.

### Sauvegardes

Le SDK carte mémoire utilise maintenant des scalaires et buffers PS1 de 32 bits sur ARM64. `tools/pc/test_libmcrd_arm64.py` vérifie le vrai code SDK : création d’une carte isolée de 128 Kio, fichier, écriture/lecture, directory de 40 octets, résultat et sentinelles adjacentes. Versions normale et ASan/UBSan passent. Cela ne prouve pas encore la sauvegarde/lecture depuis l’interface du jeu. Les save states d’émulateur sont un mécanisme distinct et restent `ENOTSUP`.

## Dernier échec d’intégration et corrections récentes

Le dernier parcours complet avant les corrections récentes sortait de la saisie du nom puis abortait vers la frame 2040 :

```text
unregistered native pointer cannot fit guest storage at 0x23000200000004
GuestRuntime_EncodePointer
func_80045208
SD_SEPlay
DuelEffect_PlaySoundCommand
TextBox_BuildStep / func_80039794
Script_RunTick
Main_RunCampaign
```

Preuve : `tmp/arm64-build/newgame-debug.log`, backtrace LLDB réelle. Deux fonctions de `sound_output_state.c` lisent un descripteur PS1 avec `u8 **table`. La lecture native de huit octets concaténait la première valeur `4` et le mot adjacent `0x230002`. Les deux curseurs et six casts sont maintenant corrigés en `u8 *G32 *` dans les copies générées.

Le test `tools/pc/test_sound_bank_pointers.py` rejoue les vraies fonctions `func_80045208` et `func_80045334`, avec ces sentinelles et trois aliases PS1. **Revalidé pendant la rédaction du handoff : succès.** Un nouveau parcours de campagne après cette correction reste à effectuer.

Les imports directs suivants disposent maintenant de bridges typés :

- `func_8016AA6C(void)` : NameEntry_Main du module chargé.
- `func_8016866C(s32)` : CampaignMap_SetLocation ; préserve l’argument signé.
- `func_80168FB4(void)` : FreeDuel_Entry.
- `func_801462B0(short, short, int, DuelEffectRequest *)` : délègue au gate existant `Memories_DuelEffectControl`, qui choisit le C retail vérifié ou l’interpréteur.

Les tests de sélection du module et du gate des effets passent ; les versions normales des deux runners ont été revalidées pendant ce handoff. Le gate des effets évite un conflit où un stub pouvait masquer sa vraie entrée au même token PS1.

**Attention à l’état du binaire :** `tmp/arm64-build/memories-arm64` a été reconstruit à 11:49 et contient la correction sonore et les bridges campagne/Free Duel. Mais `direct_overlay_bridges.py` a changé à 11:51 : l’entrée des effets de duel n’est pas encore intégrée au binaire. `tmp/arm64-build/tables.c` contient encore le stub fatal `func_801462B0`. Recompiler avant toute validation finale ; les fichiers sources sont plus récents que l’exécutable.

## Reprise recommandée, dans l’ordre

1. Recompiler avec le code actuel, vérifier que le stub `func_801462B0` a disparu et que l’adresse `0x801462b0` ne mappe qu’au vrai gate voulu.
2. Rejouer le parcours nouvelle partie ci-dessous jusqu’après la frame 2100. Capturer la scène obtenue ou le prochain défaut concret ; ne pas considérer les seuls tests unitaires comme preuve de campagne jouable.
3. Poursuivre les dialogues, atteindre le premier duel, vérifier interactions et cadence dans une vraie fenêtre avec audio.
4. Tester une sauvegarde via le jeu puis relancer/charger cette sauvegarde avec un répertoire utilisateur isolé.
5. Évaluer les autres routes importantes : Free Duel, retour aux menus, transitions de modules et audio. Garder les scénarios reproductibles qui découvrent de nouveaux défauts.

Audit effectué mais **correctifs pas encore implémentés** dans les copies générées :

- `DisplayEffect_BuildResourceObjects` écrit trois pointeurs dans les lignes de grille de `MenuRecord`, qui sont trois mots de 32 bits, soit 12 octets. `func_8003A440` et `func_80039F90` lisent ces mêmes lignes avec des vues de pointeurs natifs. Adapter signatures/définitions à `DisplayObject *G32 *`, `u8 *G32 *`, `void *G32 *` et les casts/curseurs de `display_effect_update_callbacks.c`. Tester les vrais lecteurs/écrivains avec sentinelles autour des 12 octets.
- `model_slot_row_tables.c` lit des membres de ressources de quatre octets via `*(u8 **)` : `ctx+0`, `ctx+0x14`, `arg1+0x10`, `e+4`, `e+0`, `p3+0`. Confirmer chaque provenance et corriger les vues internes G32 de façon bornée ; ne pas changer automatiquement tous les `**` du repo.
- Trois imports des crédits (`801807B0`, `80181C4C`, `80180A24`) n’ont pas de cible C correspondante ; il faudra un bridge typé vers l’interpréteur du module chargé si cette route est exercée.
- Six imports `alternate_location` sont volontairement fatals : README prouve que certaines adresses correspondent aux intérieurs de fonctions et que `80169230` est une table de données. **Ne pas inventer d’aliases** vers des fonctions voisines.

## Commandes et scénario reproductible

Depuis `/Users/vincentmetton/Code/FM/new-port` :

```sh
python3 tools/pc/build_arm64.py
python3 tools/pc/run_arm64.py
```

Le launcher utilise par défaut le disque utilisateur ci-dessus et `tmp/arm64-build/user`, désactive la recherche de mise à jour. Enter = Start, X = Cross ; flèches pour naviguer. `--no-optimize` conserve le chemin de diagnostic lent. Les dépendances ARM64 sont sous `tmp/pc/sdl-arm64/install` ; ne pas modifier les sources SDL, dont les instructions interdisent les contributions générées par IA.

Le helper temporaire `tmp/arm64-build/run_smoke.py` est présent et attend au plus 60 secondes, puis termine uniquement son enfant. Pour le parcours qui a révélé l’échec :

```sh
SMOKE_FRAME=2100 \
SMOKE_USER=tmp/arm64-build/gameplay-test \
MEMORIES_TRACE_NAME=1 \
MEMORIES_INPUT='700:0008,712:0000,800:4000,812:0000,950:4000,956:0000,1200:4000,1206:0000,1300:0008,1306:0000,1400:4000,1406:0000,1550:4000,1556:0000,1700:4000,1706:0000,1800:4000,1806:0000,1900:4000,1906:0000,2000:4000,2006:0000' \
python3 tmp/arm64-build/run_smoke.py
```

Les valeurs ci-dessus sont les bits matériels de la manette : Start `0008`, Cross `4000`. Les traces internes affichent d’autres bits après décodage : ne pas les recopier dans le script. Start 570 est trop tôt pour la séquence optimisée ; utiliser 700. La première confirmation à 950 ferme le message « Input your NAME! », celle à 1200 écrit A, Start 1300 place sur END. Les confirmations supplémentaires avancent le message multi-page ; un écran encore ouvert à 1900 n’indique pas à lui seul un bug.

Pour une fenêtre réelle, ajouter `SMOKE_WINDOW=1`. Le lancement GUI et LLDB nécessitent une exécution hors sandbox sur cette machine ; le headless peut tourner dans le sandbox. Pour des parcours plus longs, adapter explicitement la limite de 60 secondes du helper. Ne pas exécuter deux helpers en parallèle : ils partagent `run-headless.log` et les noms de captures. Ne pas utiliser le répertoire utilisateur réel pour tester les sauvegardes.

## Vérification et artefacts

Tests principaux :

```sh
make basic-types check-g32
python3 tools/pc/test_native.py
python3 tools/pc/test_translated_ir.py
python3 tools/pc/test_guest_pointer_overrides.py
python3 tools/pc/test_sound_guest_storage.py
python3 tools/pc/test_sound_bank_pointers.py
python3 tools/pc/test_gsdrawot_guest_storage.py
python3 tools/pc/test_menu_entry_guest_storage.py
python3 tools/pc/test_host_renderer_boundaries.py
python3 tools/pc/test_direct_overlay_bridge.py
python3 tools/pc/test_duel_effect_bridge.py
python3 tools/pc/test_libmcrd_arm64.py
git diff --check
```

Plusieurs runners acceptent `--sanitize` ; regarder leur CLI. Les tests qui lisent l’IR généré nécessitent d’abord un build actuel. Les nombreux avertissements de layout des headers retail ne sont pas à eux seuls un échec de test. Les checks `basic-types`, `check-g32` et `git diff --check` passent à l’état actuel. Aucune compilation de contrôle Linux/Windows ni vérification de matching console complète n’a été effectuée.

Artifacts ignorés sous `tmp/arm64-build` : exécutable, IR `raw/` et traduit `ir/`, objets, `summary.json`, `tables.c`, logs, captures. `frame1900.png` montre le clavier et le message du code ; les captures de menus et les traces de performances sont aussi dans ce dossier. Ne pas versionner les pixels propriétaires.

Historique complémentaire : `notes/macos-arm64-investigation.md` et `notes/macos-arm64-next-step.md`. Certaines sections sont chronologiques et décrivent un état ancien ; ce handoff distingue l’état courant du résultat des essais précédents.

## État des processus et limites à l’arrêt

Pendant la rédaction, vérification des processus : **aucun `memories-arm64`, build ARM64 ou LLDB en cours**. Ne pas supposer que l’ancienne fenêtre interactive est encore ouverte. Les trois agents ont été arrêtés par une limite d’usage Codex ; leurs fichiers déjà écrits sont présents, mais leurs dernières tâches ne sont pas toutes terminées. L’audit des grilles/modèles n’a pas encore donné lieu à un correctif. Aucun objectif n’a été marqué terminé.

Le prochain résultat attendu est un nouveau parcours de campagne avec le binaire recompilé, puis un duel réellement jouable et une sauvegarde relue. Tout bilan doit conserver ces limites tant que la preuve d’intégration n’existe pas.
