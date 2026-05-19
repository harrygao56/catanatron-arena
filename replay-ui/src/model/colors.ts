import type { Color, Resource } from "./types";

export const COLOR_FILL: Record<Color, string> = {
  RED: "#d64545",
  BLUE: "#3b6dd4",
  ORANGE: "#e89234",
  WHITE: "#f4f0e6",
};

export const COLOR_STROKE: Record<Color, string> = {
  RED: "#7a1f1f",
  BLUE: "#1d3a82",
  ORANGE: "#8f4f10",
  WHITE: "#5a5752",
};

export const RESOURCE_FILL: Record<Resource, string> = {
  BRICK: "#c0573e",
  WOOD: "#3f7a3a",
  SHEEP: "#a3d96b",
  WHEAT: "#e6c252",
  ORE: "#7e8a93",
};

export const DESERT_FILL = "#e2cd96";
export const WATER_FILL = "#2f5d7a";
export const GENERIC_PORT_FILL = "#cfd6df";
