# RVC-Fabric · es-ES

| 当前键名 | 原对照表行号 | 应用文本 |
| --- | --- | --- |
| `settings.prewarmTip` | L61 | Carga automáticamente el modelo de voz actual en la tarjeta gráfica al iniciar el programa, reduciendo el tiempo de espera al activar la conversión en tiempo real |
| `glossary.terms.hubert.detail` | L62 | Extrae las características de contenido fonético del habla (separando la información del timbre del hablante) y es un modelo base indispensable para todas las tareas de conversión y entrenamiento de voz. |
| `glossary.terms.directml.detail` | L63 | Solución general de aceleración por hardware en Windows para tarjetas gráficas AMD y gráficas integradas; admite la inferencia de conversión de voz, pero por ahora no admite el entrenamiento de modelos. |
| `glossary.terms.sr.detail` | L64 | Número de muestras de audio capturadas por segundo. En la conversión en tiempo real puede seguir la frecuencia de muestreo de la tarjeta de sonido o la del modelo de voz; por lo general se recomienda mantener el ajuste predeterminado. |
| `glossary.terms.wasapi.detail` | L65 | Protocolo nativo de canales de audio de Windows. El modo exclusivo reduce aún más la latencia, pero exige mayor compatibilidad de hardware en la tarjeta de sonido e impide que otros programas accedan simultáneamente al dispositivo de audio. |
| `glossary.terms.block.detail` | L66 | Duración de cada fragmento de audio enviado al modelo en un solo cálculo. Cuanto menor sea el valor, menor será la latencia, pero mayor la carga de cálculo del hardware; un valor demasiado bajo puede provocar cortes o distorsión. |
| `glossary.terms.crossfade.detail` | L67 | Duración del fundido cruzado en la unión de fragmentos de audio adyacentes para eliminar chasquidos de empalme. Un valor demasiado pequeño puede producir clics y uno demasiado grande puede apagar el sonido. |
| `glossary.terms.vbcable.detail` | L69 | Controlador de cable de audio virtual: dirija la salida convertida de RVC Fabric hacia la entrada de la tarjeta de sonido virtual y seleccione la salida virtual correspondiente como micrófono en su programa de llamadas o transmisión para enviar su voz convertida. |
| `msg.sep.no_request` | L79 | Falta el parámetro del archivo de solicitud |
| `msg.sep.empty_fields` | L80 | El modelo, la ruta de entrada y la ruta de salida no pueden estar vacíos |
| `msg.ckpt.info_saved` | L81 | Información del modelo guardada |
| `msg.ckpt.extracted` | L82 | Modelo de inferencia extraído |
| `msg.sts.model_is_archive` | L83 | El archivo seleccionado es un punto de control de entrenamiento (comienza por G_ o D_) y no puede utilizarse directamente para la conversión de voz.<br>Conviértalo primero en un modelo de voz en «Ajustes avanzados → Extracción de modelos» de la ventana de entrenamiento. |
| `msg.train.no_slices` | L84 | No se encontraron fragmentos de audio segmentados; compruebe si el conjunto de datos contiene archivos de audio legibles |
| `msg.train.oom` | L85 | Memoria de tarjeta gráfica insuficiente. Reduzca el tamaño de lote (Batch Size) o cierre otros programas que ocupen memoria gráfica e inténtelo de nuevo<br>Tamaño de lote actual: {batch}<br>{log} |
| `msg.train.resume_f0_partial` | L86 | Se detectó que la extracción previa de tono completó {done}/{total}; continuando con la parte restante… |
| `msg.train.resume_feature_partial` | L87 | Se detectó que la extracción previa de características de voz completó {done}/{total}; continuando con la parte restante… |
| `s.0f14377cdd` | L96 | Seleccione un micrófono físico; no seleccione una tarjeta de sonido virtual |
| `s.1db2e283ac` | L100 | Error de renderizado de la interfaz: {v0} |
| `s.25865a0d91` | L102 | Cambiando a la voz seleccionada… |
| `s.2898cbf891` | L103 | Normalmente se eligen auriculares o altavoces solo para monitorización local propia |
| `s.04c4e3b2b3` | L106 | Error de descarga: {e} |
| `s.37f36c5824` | L107 | Prueba de rendimiento completada：{a0} |
| `s.1455f353e7` | L114 | Error al guardar el archivo: {e} |
| `s.59f6a509e7` | L115 | Permite regular la ganancia de volumen de salida tras la conversión para equilibrar el volumen final |
| `s.63d89cdb5c` | L118 | Si tiene varias tarjetas gráficas NVIDIA instaladas, elija aquí cuál utilizar; el orden numérico no representa el rendimiento de la tarjeta |
| `s.703e6f531a` | L121 | Verificando y descomprimiendo archivos de componentes de gran tamaño; no es posible mostrar un porcentaje exacto en esta etapa, espere por favor… |
| `s.7764d6bdd2` | L123 | El servicio en segundo plano no se está ejecutando |
| `s.7dc4ea39fd` | L125 | El proceso de entrenamiento finalizó sin devolver resultados; despliegue el registro inferior para investigar la causa |
| `s.9d7d0dbc49` | L127 | Conectando: {a0} |
| `s.bc94a9c280` | L131 | Opción avanzada; por lo general se recomienda mantener el valor predeterminado |
| `s.c96a64f150` | L134 | Instrucciones de conexión de tarjeta de sonido externa |
| `s.f5b3cef9e1` | L136 | La compresión dinámica se activa cuando el sonido supera este valor en decibelios; cuanto menor sea el umbral, mayor será la compresión |
| `s.f7271a7905` | L137 | El proceso de conversión de voz terminó sin generar ningún archivo de salida; revise el registro para más detalles |
| `s.f9e62f8c38` | L138 | La prueba de rendimiento finalizó, pero no se generó ningún archivo de informe |
| `s.ckptModelAHint` | L150 | Modelo principal (modelo de inferencia base A durante la fusión) |
| `s.ckptAlphaHint` | L151 | Proporción de peso del modelo A: 1,0 conserva totalmente A, 0,0 conserva totalmente B y 0,5 mezcla ambos a partes iguales |
| `s.ckptVersionHint` | L152 | La arquitectura estándar actual es v2; seleccione v1 únicamente para modelos antiguos compatibles |
| `s.ckptChangeHint` | L154 | Permite modificar la información descriptiva incrustada en el archivo del modelo de inferencia. Haga clic primero en «Ver» para leer los datos actuales antes de editarlos |
| `s.ckptOnnxOutAuto` | L156 | Si se deja en blanco, se guardará de forma predeterminada en el mismo directorio del modelo original (archivo .onnx con el mismo nombre) |
| `s.trainSaveWeights` | L157 | Exporta un modelo de inferencia adicional listo para usar en cada intervalo de guardado |
| `s.trainGuideQ6` | L159 | ¿Cómo se utiliza tras finalizar el entrenamiento? ¿Cómo se recupera si se cierra el programa a mitad del proceso? |
| `s.dspTipFxTremolo` | L177 | Modulación de trémolo: regula periódicamente la envolvente de volumen para recrear un efecto de radio antigua o voz temblorosa |
| `s.dspTipFxChorus` | L178 | Efecto de coro (Chorus): superpone varias señales con microdesplazamiento de retardo para crear la sensación amplia de varias personas hablando al unísono |
| `s.dspTipFxBitcrush` | L179 | Reducción de muestreo y profundidad de bits (Bitcrush): reduce la precisión de cuantificación de audio para recrear la textura de baja fidelidad de los videojuegos retro |
| `s.dspTipFxSweep` | L180 | Barrido de tono en onda triangular: desliza el tono periódicamente de un extremo a otro dentro del intervalo de semitonos configurado |
| `s.dspTipFxPgate` | L181 | Salto de tono en onda cuadrada: alterna el tono de forma escalonada entre dos niveles configurados |
| `s.dspTipFxRectify` | L182 | Distorsión de rectificación de media onda: recorta el semiciclo negativo de la onda, produciendo una intensa distorsión armónica similar a un altavoz dañado |
| `s.dspTipFxReverse` | L183 | Inversión por fragmentos: reproduce fragmentos cortos de audio en tiempo real en orden inverso, generando una peculiar sensación de habla invertida |
| `s.dspTipFxRevecho` | L184 | Reverberación de cola inversa: atenúa el habla reciente en orden inverso y la mezcla en la cola de reverberación para crear una atmósfera profunda y espectral |
| `s.dspTipPRate` | L185 | Velocidad de cambio de la modulación o del barrido |
| `s.dspTipPDepth` | L186 | Proporción de intensidad de la profundidad de modulación |
| `s.dspTipPVoices` | L187 | Número de voces superpuestas (cuantas más voces, más denso sonará el coro) |
| `s.dspTipPTimeMs` | L188 | Tiempo de retardo del eco (en milisegundos) |
| `s.dspTipPLo` | L190 | Límite inferior de semitonos para el barrido de tono |
| `s.dspTipPHi` | L190 | Límite superior de semitonos para el barrido de tono |
| `s.micTestSilent` | L213 | No se detecta señal de entrada de audio. Compruebe la conexión del micrófono, el estado de silencio del sistema o pruebe a cambiar a otro dispositivo de entrada |
| `s.extraRemoveBusy` | L214 | Este componente se está descargando actualmente; espere a que termine o cancele la descarga antes de eliminarlo |
| `s.tearAskBlock` | L218 | Se detectó una carga elevada de procesamiento de audio (pueden producirse cortes o chasquidos). ¿Desea ampliar automáticamente la latencia por bloque y reiniciar la conversión de voz? |
| `s.faqDownloadSlowH` | L222 | Admite reanudación de descargas; al reintentar continuará desde la posición ya descargada. |
| `s.faqLatencyQ` | L223 | ¿Por qué existe un retraso apreciable entre hablar y escuchar la voz convertida? |
| `s.chkSnapshotModel` | L225 | El archivo de modelo seleccionado parece ser un punto de control de entrenamiento (comienza por G_ o D_) y no puede utilizarse directamente para la conversión de voz<br>{name} |
| `s.errActDownload` | L226 | Ir a descargas |
| `s.errActRuntime` | L226 | Configurar entorno de ejecución |
| `s.errActExtract` | L226 | Ir a extracción de modelo |
| `s.errActBatch` | L226 | Ajustar parámetros de entrenamiento |
| `s.trainSrCost` | L227 | Cuanto mayor sea la frecuencia de muestreo, más ricos serán los detalles de alta frecuencia, pero también aumentará el uso de memoria gráfica; elija una frecuencia menor si la memoria gráfica es limitada. |
| `s.trainStagesIncomplete` | L229 | Se detectaron pasos previos de preprocesamiento sin completar. Al continuar el entrenamiento se completará automáticamente el preprocesamiento pendiente. |
| `s.cleanupDataset` | L231 | Limpiar archivos temporales del conjunto de datos (fragmentos cortados y caché de características) |
| `s.voiceDeleteFailed` | L232 | Error al eliminar. Es posible que esta voz esté en uso; detenga primero la conversión en tiempo real o espere a que finalice la tarea de conversión antes de volver a intentarlo.<br>{e} |
| `s.devAutoNoList` | L234 | Espere a que el motor de audio termine de iniciarse antes de ejecutar la configuración automática |
| `s.guide.notice.detail` | L237 | Al informar de un problema, indique los pasos específicos realizados, los mensajes mostrados en pantalla y la etapa en la que ocurrió la anomalía. |
| `crop.previewBeforeNote` | L241 | Las imágenes verticales solo muestran su zona central en las tarjetas de voz; utilice el recorte para ajustar el área visible |
