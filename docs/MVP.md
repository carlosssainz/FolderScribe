# FolderScribe — Alcance del MVP

## 1. Objetivo

Escanear una carpeta de prueba en Ubuntu 24.04, mostrar un inventario fiable
del contenido y preparar propuestas supervisadas de clasificación y renombrado
sin modificar ningún archivo durante el análisis.

El MVP demuestra que FolderScribe puede leer el sistema de archivos, extraer
información útil de los documentos y presentar al usuario decisiones
accionables que él mismo debe aprobar antes de ejecutar.

## 2. Funcionalidades incluidas

Se implementan de forma progresiva, no necesariamente en el orden listado:

- **Formatos soportados:** PDF, DOCX, TXT, Markdown.
- **Selección de carpeta de origen.** El usuario elige el directorio a
  organizar.
- **Inventario recursivo.** Lista completa de archivos, subdirectorios y
  estructura actual.
- **Identificación de formatos compatibles y no compatibles.** Cada archivo se
  etiqueta como soportado o no según su tipo MIME.
- **Exclusiones.** El usuario puede excluir archivos, carpetas o patrones.
- **No seguir enlaces simbólicos.** Los enlaces simbólicos se listan pero no se
  siguen ni procesan.
- **Detección y omisión de proyectos de código.** Se identifican directorios
  con indicios de proyecto (`.git`, `node_modules`, `package.json`, etc.) y se
  excluyen del análisis.
- **Índice local.** Base de datos ligera que almacena el inventario, los
  metadatos y el historial de operaciones.
- **Duplicados exactos.** Detección mediante hash SHA-256. Los duplicados se
  señalan pero no se mueven automáticamente.
- **Extracción de texto.** Contenido textual legible para PDF, DOCX, TXT y
  Markdown.
- **Detección de PDF escaneados.** Si un PDF no contiene texto extraíble, se
  marca como candidato a OCR.
- **OCR rápido y OCR completo.** El usuario puede elegir entre OCR ligero
  (primeras páginas) o completo (todo el documento) para PDF escaneados.
- **Propuestas de clasificación.** Sugerencias de carpeta de destino basadas en
  tipo MIME, fecha, contenido y nombre.
- **Propuestas de renombrado.** Nombres descriptivos generados a partir del
  análisis.
- **Explicación y confianza.** Cada propuesta incluye una justución legible y
  un nivel de confianza (alta, media, baja).
- **Árbol actual y árbol propuesto.** Vista comparativa de la estructura antes
  y después.
- **Aprobación individual y por grupos.** El usuario puede aprobar archivo por
  archivo o seleccionar grupos enteros.
- **Creación supervisada de carpetas.** Si una carpeta propuesta no existe, se
  crea solo tras aprobación explícita.
- **Movimiento y renombrado aprobados.** Ejecución física de los cambios
  confirmados.
- **Historial de operaciones durante un mes.** Cada operación queda registrada
  con fecha, origen, destino y archivos afectados. El historial se conserva 30
  días.
- **Deshacer operaciones.** FolderScribe puede revertir un movimiento o
  renombrado ejecutado dentro del período de historial.
- **Cuatro niveles de privacidad.** Excluir, solo metadatos, local y completo,
  con configuración por archivo o por tipo.

## 3. Funcionalidades excluidas

Lo siguiente queda fuera del primer MVP:

- **Fotografías y capturas de pantalla.** No hay clasificación visual ni
  extracción de metadatos EXIF.
- **Clasificación visual.** No se analiza el contenido de imágenes ni vídeos.
- **Archivos comprimidos.** ZIP, tar, gz y similares no se desempaquetan ni
  analizan.
- **Organización de proyectos de programación.** Los directorios con código se
  detectan y se omiten, no se clasifican.
- **Vigilancia continua.** FolderScribe no monitoriza cambios en tiempo real.
- **Enlaces simbólicos avanzados.** No se resuelven cadenas de enlaces.
- **Eliminación automática.** FolderScribe nunca borra archivos.
- **Sincronización entre equipos.** No hay componente de red ni nube.
- **Plantillas compartidas.** Las reglas de organización son locales.
- **Grafo de conocimiento.** Las relaciones entre archivos no se modelan.
- **Windows.** El MVP se centra en Ubuntu 24.04. Windows se abordará tras
  estabilizar el flujo principal.

## 4. Reglas de seguridad

- **Solo lectura durante el análisis.** FolderScribe no crea, modifica, mueve
  ni elimina ningún archivo hasta la fase de ejecución aprobada.
- **Confirmación obligatoria.** No se ejecuta ninguna operación sin aprobación
  explícita del usuario, ni siquiera en lotes.
- **Límite de alcance.** El análisis se limita a la carpeta seleccionada. No se
  asciende en el árbol de directorios.
- **Deshacer garantizado.** Toda operación ejecutada debe poder revertirse
  dentro del período de historial.
- **No a proyectos de código.** Los directorios con indicios de proyecto de
  programación se omiten para evitar alterar entornos de desarrollo.
- **No a enlaces simbólicos.** No se sigue ni procesa el destino de enlaces
  simbólicos.
- **Privacidad configurable.** Por defecto, ningún dato sale del equipo (nivel
  local).

## 5. Criterios de éxito

- FolderScribe inventaria correctamente una carpeta de prueba con al menos 50
  archivos mezclando PDF, DOCX, TXT y Markdown.
- El inventario distingue formatos soportados de no soportados.
- Las propuestas de clasificación y renombrado son razonables y están
  explicadas.
- El usuario puede aprobar, corregir, crear carpetas, excluir archivos y omitir
  propuestas sin errores.
- La ejecución de cambios aprobados modifica el sistema de archivos
  exclusivamente según lo confirmado.
- El historial registra cada operación y permite deshacerla durante 30 días.
- No se procesan enlaces simbólicos ni proyectos de código.
- El nivel de privacidad local no envía ningún dato fuera del equipo.

## 6. Regla de control de alcance

Cualquier funcionalidad listada como excluida en la sección 3 no se
implementará sin modificar primero este documento. La modificación debe ser
explícita: mover el ítem de "excluido" a "incluido" y actualizar los
criterios de éxito correspondientes. Esto aplica a todo el equipo de
desarrollo.
