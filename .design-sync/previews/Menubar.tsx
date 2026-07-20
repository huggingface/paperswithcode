import * as React from "react";
import {
  Menubar,
  MenubarMenu,
  MenubarTrigger,
  MenubarContent,
  MenubarItem,
  MenubarSeparator,
  MenubarShortcut,
} from "paperswithcode";

export function Default() {
  return (
    <div style={{ padding: 20 }}>
      <Menubar>
        <MenubarMenu>
          <MenubarTrigger>Paper</MenubarTrigger>
          <MenubarContent>
            <MenubarItem>
              Add to library <MenubarShortcut>⌘L</MenubarShortcut>
            </MenubarItem>
            <MenubarItem>Cite (BibTeX)</MenubarItem>
            <MenubarSeparator />
            <MenubarItem>Report an issue</MenubarItem>
          </MenubarContent>
        </MenubarMenu>
        <MenubarMenu>
          <MenubarTrigger>Code</MenubarTrigger>
        </MenubarMenu>
        <MenubarMenu>
          <MenubarTrigger>Results</MenubarTrigger>
        </MenubarMenu>
        <MenubarMenu>
          <MenubarTrigger>Datasets</MenubarTrigger>
        </MenubarMenu>
      </Menubar>
    </div>
  );
}
