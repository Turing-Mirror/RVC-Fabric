# RVC-Fabric · fr-FR

| 当前键名 | 原对照表行号 | 应用文本 |
| --- | --- | --- |
| `settings.prewarmTip` | L61 | Charge automatiquement le modèle vocal actuel dans la mémoire de la carte graphique au démarrage afin de réduire le temps d'attente à l'activation du changement de voix |
| `glossary.terms.hubert.detail` | L62 | Extrait les caractéristiques de contenu linguistique de la parole (en isolant le timbre du locuteur) ; c'est un modèle de base indispensable à toute conversion ou entraînement vocal. |
| `glossary.terms.directml.detail` | L63 | Solution d'accélération matérielle générique sous Windows pour les cartes graphiques AMD et les GPU intégrés ; prend en charge l'inférence de conversion vocale, mais pas encore l'entraînement de modèles. |
| `glossary.terms.sr.detail` | L64 | Nombre d'échantillons audio capturés par seconde. En temps réel, vous pouvez suivre la fréquence d'échantillonnage de la carte son ou celle du modèle vocal ; il est généralement conseillé de conserver le réglage par défaut. |
| `glossary.terms.wasapi.detail` | L65 | Protocole audio natif de Windows. Le mode exclusif réduit encore la latence mais exige une stricte compatibilité matérielle et empêche les autres logiciels d'utiliser simultanément le périphérique audio. |
| `glossary.terms.block.detail` | L66 | Durée de chaque tranche audio envoyée au modèle en une passe. Plus la valeur est faible, plus la latence diminue, mais plus la charge de calcul augmente (une valeur trop basse peut provoquer des coupures ou de la distorsion). |
| `glossary.terms.crossfade.detail` | L67 | Durée du fondu enchaîné à la jonction de deux tranches audio consécutives afin d'éliminer les clics de raccord. Une valeur trop courte produit des clics ; une valeur trop longue assourdit le son. |
| `glossary.terms.vbcable.detail` | L69 | Pilote de câble audio virtuel : dirigez la sortie convertie de RVC Fabric vers l'entrée de la carte son virtuelle, puis choisissez la sortie virtuelle correspondante comme microphone dans votre jeu ou logiciel d'appel pour transmettre votre voix modifiée. |
| `msg.sep.no_request` | L79 | Paramètre de fichier de requête manquant |
| `msg.sep.empty_fields` | L80 | Le modèle, le chemin d'entrée et le chemin de sortie ne peuvent pas être vides |
| `msg.ckpt.info_saved` | L81 | Informations du modèle enregistrées |
| `msg.ckpt.extracted` | L82 | Modèle d'inférence extrait |
| `msg.sts.model_is_archive` | L83 | Le fichier sélectionné est un point de contrôle d'entraînement (commençant par G_ ou D_) et ne peut pas être utilisé directement pour la conversion vocale.<br>Convertissez-la d'abord en modèle de voix via « Réglages avancés → Extraction de modèle » dans la fenêtre d'entraînement. |
| `msg.train.no_slices` | L84 | Aucun segment audio découpé n'a été trouvé ; veuillez vérifier que le jeu de données contient des fichiers audio lisibles |
| `msg.train.oom` | L85 | Mémoire vidéo (VRAM) insuffisante. Réduisez la taille de lot (Batch Size) ou fermez les autres applications utilisant la carte graphique avant de réessayer<br>Taille de lot actuelle: {batch}<br>{log} |
| `msg.train.resume_f0_partial` | L86 | Extraction précédente des caractéristiques de hauteur détectée à {done}/{total} ; reprise sur les éléments restants… |
| `msg.train.resume_feature_partial` | L87 | Extraction précédente des caractéristiques vocales détectée à {done}/{total} ; reprise sur les éléments restants… |
| `s.0f14377cdd` | L96 | Veuillez sélectionner un microphone physique et non une carte son virtuelle |
| `s.1db2e283ac` | L100 | Erreur de rendu de l'interface : {v0} |
| `s.25865a0d91` | L102 | Basculement vers la voix sélectionnée… |
| `s.2898cbf891` | L103 | Choisissez généralement votre casque ou vos haut-parleurs pour votre écoute personnelle uniquement |
| `s.04c4e3b2b3` | L106 | Échec du téléchargement : {e} |
| `s.37f36c5824` | L107 | Test de performances terminé：{a0} |
| `s.1455f353e7` | L114 | Échec de l'enregistrement du fichier : {e} |
| `s.59f6a509e7` | L115 | Permet d'ajuster le gain de volume en sortie après conversion afin d'équilibrer le niveau sonore final |
| `s.63d89cdb5c` | L118 | Permet de choisir la carte graphique dédiée au calcul lorsque plusieurs GPU NVIDIA sont installés ; l'ordre d'indexation n'indique pas le niveau de performance |
| `s.703e6f531a` | L121 | Vérification et extraction d'archives volumineuses en cours ; le pourcentage exact ne peut pas être affiché à cette étape, veuillez patienter… |
| `s.7764d6bdd2` | L123 | Le service d'arrière-plan n'est pas en cours d'exécution |
| `s.7dc4ea39fd` | L125 | Le processus d'entraînement s'est arrêté sans renvoyer de résultat ; veuillez développer le journal en bas de page pour en rechercher la cause |
| `s.9d7d0dbc49` | L127 | Connexion en cours : {a0} |
| `s.bc94a9c280` | L131 | Option avancée ; il est généralement recommandé de conserver la valeur par défaut |
| `s.c96a64f150` | L134 | Connexion d'une carte son externe |
| `s.f5b3cef9e1` | L136 | La compression dynamique se déclenche lorsque le niveau sonore dépasse cette valeur en dB ; plus le seuil est bas, plus la compression est forte |
| `s.f7271a7905` | L137 | Le processus de conversion vocale s'est terminé sans générer de fichier de sortie ; veuillez consulter les journaux |
| `s.f9e62f8c38` | L138 | Le test de performances s'est terminé sans générer de fichier de rapport |
| `s.ckptModelAHint` | L150 | Modèle principal (modèle d'inférence de référence A lors de la fusion) |
| `s.ckptAlphaHint` | L151 | Pondération du modèle A : 1,0 conserve uniquement A, 0,0 conserve uniquement B, et 0,5 mélange les deux à parts égales |
| `s.ckptVersionHint` | L152 | L'architecture standard actuelle est la v2 ; ne sélectionnez la v1 que pour d'anciens modèles compatibles |
| `s.ckptChangeHint` | L154 | Permet de modifier les métadonnées descriptives intégrées au fichier de modèle d'inférence. Cliquez d'abord sur « Afficher » pour lire les informations existantes avant de les modifier |
| `s.ckptOnnxOutAuto` | L156 | Laissez vide pour enregistrer par défaut dans le même dossier que le modèle d'origine (fichier .onnx du même nom) |
| `s.trainSaveWeights` | L157 | Exporte à chaque intervalle de sauvegarde un modèle d'inférence léger directement utilisable |
| `s.trainGuideQ6` | L159 | Comment utiliser le modèle une fois l'entraînement terminé ? Comment reprendre après une fermeture en cours de route ? |
| `s.dspTipFxTremolo` | L177 | Modulation de trémolo : fait osciller périodiquement l'enveloppe de volume pour créer un effet de vieille radio ou de voix tremblante |
| `s.dspTipFxChorus` | L178 | Effet de chœur (Chorus) : superpose plusieurs signaux légèrement décalés afin de créer l'impression d'un groupe parlant à l'unisson |
| `s.dspTipFxBitcrush` | L179 | Réduction d'échantillonnage et de résolution (Bitcrush) : abaisse la précision de quantification audio pour reproduire le grain lo-fi des consoles rétro |
| `s.dspTipFxSweep` | L180 | Balayage de hauteur en onde triangulaire : fait glisser périodiquement la hauteur entre deux limites en demi-tons |
| `s.dspTipFxPgate` | L181 | Saut de hauteur en onde carrée : fait basculer brusquement la hauteur entre deux paliers configurés |
| `s.dspTipFxRectify` | L182 | Distorsion par redressement demi-onde : supprime l'alternance négative du signal pour produire une forte distorsion harmonique évoquant un haut-parleur saturé |
| `s.dspTipFxReverse` | L183 | Inversion granulaire : lit à l'envers de courts segments audio en temps réel pour un effet d'élocution inversée |
| `s.dspTipFxRevecho` | L184 | Réverbération à queue inversée : mêle les paroles récentes inversées à la traînée de réverbération pour une atmosphère spectrale |
| `s.dspTipPRate` | L185 | Vitesse de variation de la modulation ou du balayage |
| `s.dspTipPDepth` | L186 | Intensité de la profondeur de modulation |
| `s.dspTipPVoices` | L187 | Nombre de voix superposées (plus il y a de voix, plus l'effet de chœur est ample) |
| `s.dspTipPTimeMs` | L188 | Temps de retard de l'écho (en millisecondes) |
| `s.dspTipPLo` | L190 | Limite inférieure du balayage de hauteur (en demi-tons) |
| `s.dspTipPHi` | L190 | Limite supérieure du balayage de hauteur (en demi-tons) |
| `s.micTestSilent` | L213 | Aucun signal d'entrée audio détecté. Veuillez vérifier le branchement du microphone, les paramètres de sourdine du système ou essayer un autre périphérique d'entrée |
| `s.extraRemoveBusy` | L214 | Ce composant est en cours de téléchargement ; veuillez attendre la fin ou annuler le téléchargement avant de le supprimer |
| `s.tearAskBlock` | L218 | Charge de traitement audio élevée détectée (risque de coupures ou de craquements). Voulez-vous augmenter automatiquement la taille de bloc et relancer la conversion vocale ? |
| `s.faqDownloadSlowH` | L222 | La reprise de téléchargement est prise en charge ; une nouvelle tentative reprendra à partir des données déjà reçues. |
| `s.faqLatencyQ` | L223 | Pourquoi y a-t-il un décalage perceptible entre le moment où je parle et celui où j'entends la voix convertie ? |
| `s.chkSnapshotModel` | L225 | Le fichier modèle sélectionné semble être un point de contrôle d'entraînement (commençant par G_ ou D_) et ne peut pas être utilisé directement pour la conversion vocale<br>{name} |
| `s.errActDownload` | L226 | Aller aux téléchargements |
| `s.errActRuntime` | L226 | Configurer l'environnement |
| `s.errActExtract` | L226 | Aller à l'extraction de modèle |
| `s.errActBatch` | L226 | Ajuster les paramètres d'entraînement |
| `s.trainSrCost` | L227 | Plus la fréquence d'échantillonnage est élevée, plus les hautes fréquences sont détaillées, mais plus l'occupation de la mémoire vidéo augmente ; privilégiez une fréquence plus basse si votre mémoire vidéo est limitée. |
| `s.trainStagesIncomplete` | L229 | Des étapes de prétraitement inachevées ont été détectées. La poursuite de l'entraînement complétera automatiquement les prétraitements manquants. |
| `s.cleanupDataset` | L231 | Nettoyer les fichiers temporaires du jeu de données (segments découpés et caches de caractéristiques) |
| `s.voiceDeleteFailed` | L232 | Échec de la suppression. Ce modèle vocal est peut-être en cours d'utilisation ; veuillez arrêter la conversion en temps réel ou attendre la fin de la tâche en cours avant de réessayer.<br>{e} |
| `s.devAutoNoList` | L234 | Veuillez attendre la fin du démarrage du moteur audio avant de lancer la configuration automatique |
| `s.guide.notice.detail` | L237 | Lors d'un signalement, veuillez préciser les opérations effectuées, les messages affichés à l'écran ainsi que l'étape exacte où l'anomalie est apparue. |
| `crop.previewBeforeNote` | L241 | Les images verticales n'affichent que leur zone centrale sur les cartes de voix ; utilisez le recadrage pour ajuster la zone visible |
