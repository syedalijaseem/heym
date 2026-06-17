declare module "grid-layout-plus" {
  import type { DefineComponent } from "vue";

  export const GridLayout: DefineComponent<Record<string, unknown>, object, unknown>;
  export const GridItem: DefineComponent<Record<string, unknown>, object, unknown>;
}
