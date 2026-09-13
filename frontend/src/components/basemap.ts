import type { ExpressionSpecification, Map as MapLibreMap, MapOptions } from "maplibre-gl";

// OpenFreeMap: OpenStreetMap data served free with no API key and no usage limits, styled for MapLibre.
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

// every map in the app shows exactly one world
//
// renderWorldCopies: false is enough on its own: MapLibre then stops zooming out once the world spans the map's width.
// don't add maxBounds of the whole world alongside it; bounds touching ±180 collapse to nothing,
// and MapLibre responds by jumping to its maximum zoom on the antimeridian
export const BASEMAP_OPTIONS: Pick<MapOptions, "style" | "renderWorldCopies" | "attributionControl" | "center" | "zoom"> = {
  style: BASEMAP_STYLE,
  renderWorldCopies: false,
  // open fully zoomed out; asking for 0 settles at the widest zoom where the one world still fills the map
  center: [0, 20],
  zoom: 0,
  // OpenStreetMap data has to be credited; compact keeps it to a small toggle in the corner
  attributionControl: { compact: true },
};

// the English name where OpenStreetMap has one, then the Latin-script name, then whatever the place is locally called
const ENGLISH_NAME: ExpressionSpecification = ["coalesce", ["get", "name:en"], ["get", "name_en"], ["get", "name:latin"], ["get", "name"]];

// the style labels places in Latin and local script together ("Mumbai मुंबई"); the app shows English only
export function showEnglishLabels(map: MapLibreMap): void {
  map.on("style.load", () => {
    for (const layer of map.getStyle().layers) {
      if (layer.type !== "symbol") continue;
      const field = layer.layout?.["text-field"];
      // only name labels; road shields show route numbers ("ref") and stay as they are
      if (field && JSON.stringify(field).includes('"name')) map.setLayoutProperty(layer.id, "text-field", ENGLISH_NAME);
    }
  });
}
