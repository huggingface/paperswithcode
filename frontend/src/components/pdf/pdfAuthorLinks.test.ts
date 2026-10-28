import { describe, expect, it } from "vitest";
import { findPdfAuthorNames, type PdfAuthor, type PdfTextRun } from "./pdfAuthorLinks";

const runs = (...texts: string[]): PdfTextRun[] => texts.map((text, item) => ({ text, item }));

function linked(texts: string[], authors: PdfAuthor[]): string[] {
  const page = runs(...texts);
  return findPdfAuthorNames(page, authors).map(({ authorId, start, end }) => {
    const text = page.slice(start.run, end.run + 1).map((run, index) => run.text.slice(
      index === 0 ? start.offset : 0,
      start.run + index === end.run ? end.offset : run.text.length,
    )).join("|");
    return `${authorId}:${text}`;
  });
}

const longformer = [
  { id: "6438", name: "Iz Beltagy" },
  { id: "9515", name: "Matthew E. Peters" },
  { id: "908", name: "Arman Cohan" },
];

describe("findPdfAuthorNames", () => {
  it("links each author on a typical author line, across text items and affiliation marks", () => {
    expect(linked(["Longformer: The Long-Document Transformer", "Iz Beltagy", "∗", "Matthew E. Peters", "∗", "Arman", " ", "Cohan", "∗"], longformer))
      .toEqual(["6438:Iz Beltagy", "9515:Matthew E. Peters", "908:Arman| |Cohan"]);
    expect(linked(["Iz Beltagy1,2, Matthew E. Peters2 and Arman Cohan1"], longformer))
      .toEqual(["6438:Iz Beltagy", "9515:Matthew E. Peters", "908:Arman Cohan"]);
  });

  it("never links email addresses", () => {
    expect(linked(["{iz.beltagy, Arman.Cohan@allenai.org}", "beltagy@allenai.org"], longformer)).toEqual([]);
  });

  it("never links across punctuation or into longer words", () => {
    const authors = [{ id: "1", name: "Li Jun" }, { id: "2", name: "Wei Li" }];
    expect(linked(["Zhang Wei Li, Jun Zhang"], authors)).toEqual(["2:Wei Li"]);
    expect(linked(["Weili Jung and Xiwei Lin"], authors)).toEqual([]);
    expect(linked(["Jo Hannah"], [{ id: "1", name: "Joh Annah" }])).toEqual([]);
  });

  it("prefers the longer of two authors' overlapping names", () => {
    const authors = [{ id: "1", name: "Wei Li" }, { id: "2", name: "Hong-Wei Li" }];
    expect(linked(["Hong-Wei Li and Wei Li"], authors)).toEqual(["2:Hong-Wei Li", "1:Wei Li"]);
  });

  it("links no one whose spelling another author shares", () => {
    const authors = [{ id: "1", name: "Wei Li" }, { id: "2", name: "Wei X. Li" }, { id: "3", name: "Wei Li" }];
    expect(linked(["Wei Li, Wei X. Li"], authors)).toEqual(["2:Wei X. Li"]);
  });

  it("ignores single-word and very short names", () => {
    expect(linked(["Sora and Bo Q."], [{ id: "1", name: "Sora" }, { id: "2", name: "Bo Q" }])).toEqual([]);
  });

  it("tolerates middle initials missing on either side", () => {
    expect(linked(["Scott M. Lundberg"], [{ id: "1", name: "Scott Lundberg" }])).toEqual(["1:Scott M. Lundberg"]);
    expect(linked(["Ed H. Chi, Quoc V. Le"], [{ id: "1", name: "Ed Chi" }, { id: "2", name: "Quoc Le" }]))
      .toEqual(["1:Ed H. Chi", "2:Quoc V. Le"]);
    expect(linked(["Matthew Peters"], longformer)).toEqual(["9515:Matthew Peters"]);
  });

  it("matches accents however the PDF encodes them, and all-caps names", () => {
    const authors = [{ id: "1", name: "Andreas Müller" }, { id: "2", name: "Lukasz Kaiser" }, { id: "3", name: "Martín Abadi" }];
    expect(linked(["Andreas M¨", "uller, Łukasz Kaiser, Mart´", "ın Abadi"], authors))
      .toEqual(["1:Andreas M¨|uller", "2:Łukasz Kaiser", "3:Mart´|ın Abadi"]);
    expect(linked(["ANDREAS MÜLLER"], authors)).toEqual(["1:ANDREAS MÜLLER"]);
  });

  it("requires a capitalized stored name to be capitalized in the text", () => {
    expect(linked(["the iz beltagy dataset"], longformer)).toEqual([]);
  });
});
