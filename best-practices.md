# MAUP Best Practice Guidelines
Last updated on June 16th, 2021 by Max Fan (@InnovativeInventor).

*Note: Some features are only available in `maup`'s `1.0` release.*

## Introduction
Prorating votes from one set of geometries to another is a tricky business. 
The [MAUP problem](https://en.wikipedia.org/wiki/Modifiable_areal_unit_problem) is inherently difficult to address, as any solution requires relying on various statistical assumptions. 

Even the most common invocation of `maup` (prorating vote data by population), entails several assumptions:

- Perfect tiling of source and target geometries without holes or overlaps
- For any given region, population is greater than or equal to the number of votes cast
- Uniformly proportional voter turnout (this is practically unavoidable)

Other invocations of `maup` may include more assumptions. For example, assigning block-level data to precincts by greatest shared area also entails the added assumption that 

If not properly understood and managed, these assumptions could introduce serious biases in the final data product.

## Best Practices Checklist
- [ ] Ensure that source and target geometries are perfectly tiled and well-formed by using the `maup.doctor(source, target)` tool, which will return `True` if the source and/or target is well-formed.
- [ ] Resolve tiling, overlap, and gap issues manually or by using `maup.resolve_overlaps()`, `maup.close_gaps()`, and `maup.autofix()` as needed with low relative_threshold tolerances.
- [ ] Ensure that you are prorating by population, not area.
- [ ] Ensure your weights are normalized by calling `maup.normalize(weights, level=0)`.
- [ ] If you are aggregating/disaggregating data, use a blessed method of invoking `maup`, as shown in the [README](https://github.com/mggg/maup#readme). Other methods are not guaranteed to work and should be used with deliberate care.

## Filing Bug Reports and Support
Contributions and bug reports are welcome! 
If `maup.doctor()` returns `True` and you encounter an issue (you get an error or votes go missing), then it is vital that you file a bug report! 
If you encounter other issues, bug reports are also welcome!

