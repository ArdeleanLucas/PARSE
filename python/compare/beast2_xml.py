"""Wrap a binary NEXUS character matrix into a runnable BEAST 2.7 XML.

This bridges the last step of the phylogenetic export: PARSE produces a NEXUS
cognate matrix, but BEAST2 runs its own XML. ``nexus_to_beast2_xml`` parses the
binary matrix and emits a minimal, self-contained BEAST 2.7 analysis (binary
substitution model, Yule tree prior, strict clock) that BEAST2 accepts without
BEAUti or any external script.

The template is intentionally a sensible *default* for a runnable analysis, not a
tuned study design: rates and clock are fixed, frequencies are estimated, and the
chain length is caller-controlled. Downstream model choices (clock model, tree
prior, site heterogeneity) remain the researcher's to refine.
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

DEFAULT_CHAIN_LENGTH = 10000000

# Element-name aliases BEAST's parser needs to resolve <prior>, <Uniform>, etc.
_MAPS = [
    ("Uniform", "beast.base.inference.distribution.Uniform"),
    ("Exponential", "beast.base.inference.distribution.Exponential"),
    ("LogNormal", "beast.base.inference.distribution.LogNormalDistributionModel"),
    ("Normal", "beast.base.inference.distribution.Normal"),
    ("Beta", "beast.base.inference.distribution.Beta"),
    ("Gamma", "beast.base.inference.distribution.Gamma"),
    ("LaplaceDistribution", "beast.base.inference.distribution.LaplaceDistribution"),
    ("prior", "beast.base.inference.distribution.Prior"),
    ("InverseGamma", "beast.base.inference.distribution.InverseGamma"),
    ("OneOnX", "beast.base.inference.distribution.OneOnX"),
]

_NAMESPACE = (
    "beast.base.evolution.alignment:beast.base.evolution.tree:"
    "beast.base.evolution.tree.coalescent:beast.base.evolution.speciation:"
    "beast.base.evolution.sitemodel:beast.base.evolution.substitutionmodel:"
    "beast.base.evolution.branchratemodel:beast.base.evolution.likelihood:"
    "beast.base.evolution.operator:beast.base.evolution:"
    "beast.base.inference:beast.base.inference.distribution:"
    "beast.base.inference.operator:beast.base.inference.parameter:"
    "beast.pkgmgmt:beast.base.core:beast.base.util"
)


def parse_nexus_matrix(nexus_text: str) -> Tuple[List[Tuple[str, str]], int]:
    """Return ``([(taxon, sequence), ...], nchar)`` from a binary NEXUS matrix."""
    match = re.search(r"MATRIX\s*(.*?);", nexus_text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError("No MATRIX block found in NEXUS text.")
    seqs: List[Tuple[str, str]] = []
    for line in match.group(1).splitlines():
        parts = line.split()
        if len(parts) >= 2 and set(parts[1]) <= set("01?-"):
            seqs.append((parts[0], parts[1]))
    if not seqs:
        raise ValueError("No binary sequences parsed from MATRIX block.")
    nchar = len(seqs[0][1])
    ragged = [tax for tax, s in seqs if len(s) != nchar]
    if ragged:
        raise ValueError("Ragged matrix: sequences differ in length ({0}).".format(ragged))
    return seqs, nchar


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def nexus_to_beast2_xml(
    nexus_text: str,
    *,
    chain_length: int = DEFAULT_CHAIN_LENGTH,
    alignment_id: str = "cognates",
) -> str:
    """Convert a binary NEXUS character matrix into a runnable BEAST 2.7 XML."""
    seqs, _nchar = parse_nexus_matrix(nexus_text)
    chain = int(chain_length)
    if chain < 1:
        raise ValueError("chain_length must be a positive integer.")

    maps_xml = "\n".join('  <map name="{0}">{1}</map>'.format(n, c) for n, c in _MAPS)
    seq_xml = "\n".join(
        '    <sequence taxon="{0}" value="{1}"/>'.format(_escape(tax), s) for tax, s in seqs
    )
    log_every = max(1, chain // 200)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<beast version="2.7" namespace="{_NAMESPACE}">

{maps_xml}

  <data id="{alignment_id}" spec="Alignment" dataType="binary">
{seq_xml}
  </data>

  <run id="mcmc" spec="MCMC" chainLength="{chain}">
    <state id="state" storeEvery="5000">
      <tree id="Tree" spec="Tree" name="stateNode">
        <taxonset id="TaxonSet" spec="TaxonSet">
          <alignment idref="{alignment_id}"/>
        </taxonset>
      </tree>
      <parameter id="birthRate" spec="parameter.RealParameter" name="stateNode" value="1.0"/>
      <parameter id="freqParameter" spec="parameter.RealParameter" dimension="2" lower="0.0" upper="1.0" name="stateNode" value="0.5"/>
    </state>

    <init id="RandomTree" spec="RandomTree" estimate="false" initial="@Tree" taxa="@{alignment_id}">
      <populationModel id="ConstantPopulation0" spec="ConstantPopulation">
        <parameter id="randomPopSize" spec="parameter.RealParameter" name="popSize" value="1.0"/>
      </populationModel>
    </init>

    <distribution id="posterior" spec="CompoundDistribution">
      <distribution id="prior" spec="CompoundDistribution">
        <distribution id="YuleModel" spec="YuleModel" birthDiffRate="@birthRate" tree="@Tree"/>
        <prior id="YuleBirthRatePrior" name="distribution" x="@birthRate">
          <Uniform id="Uniform.0" name="distr" upper="1000.0"/>
        </prior>
      </distribution>
      <distribution id="likelihood" spec="CompoundDistribution" useThreads="true">
        <distribution id="treeLikelihood" spec="TreeLikelihood" data="@{alignment_id}" tree="@Tree">
          <siteModel id="SiteModel" spec="SiteModel">
            <parameter id="mutationRate" spec="parameter.RealParameter" estimate="false" name="mutationRate" value="1.0"/>
            <substModel id="subst" spec="GeneralSubstitutionModel">
              <parameter id="rates" spec="parameter.RealParameter" dimension="2" estimate="false" name="rates" value="1.0"/>
              <frequencies id="freqs" spec="Frequencies" frequencies="@freqParameter"/>
            </substModel>
          </siteModel>
          <branchRateModel id="StrictClock" spec="StrictClockModel">
            <parameter id="clockRate" spec="parameter.RealParameter" estimate="false" name="clock.rate" value="1.0"/>
          </branchRateModel>
        </distribution>
      </distribution>
    </distribution>

    <operator id="treeScaler" spec="ScaleOperator" scaleFactor="0.5" tree="@Tree" weight="3.0"/>
    <operator id="treeRootScaler" spec="ScaleOperator" rootOnly="true" scaleFactor="0.5" tree="@Tree" weight="3.0"/>
    <operator id="UniformOperator" spec="Uniform" tree="@Tree" weight="30.0"/>
    <operator id="SubtreeSlide" spec="SubtreeSlide" tree="@Tree" weight="15.0"/>
    <operator id="narrow" spec="Exchange" tree="@Tree" weight="15.0"/>
    <operator id="wide" spec="Exchange" isNarrow="false" tree="@Tree" weight="3.0"/>
    <operator id="WilsonBalding" spec="WilsonBalding" tree="@Tree" weight="3.0"/>
    <operator id="birthRateScaler" spec="ScaleOperator" parameter="@birthRate" scaleFactor="0.75" weight="3.0"/>
    <operator id="freqExchanger" spec="DeltaExchangeOperator" delta="0.01" parameter="@freqParameter" weight="1.0"/>

    <logger id="tracelog" fileName="$(filebase).log" logEvery="{log_every}">
      <log idref="posterior"/>
      <log idref="likelihood"/>
      <log idref="prior"/>
      <log idref="treeLikelihood"/>
      <log id="TreeHeight" spec="TreeHeightLogger" tree="@Tree"/>
      <log idref="birthRate"/>
    </logger>
    <logger id="screenlog" logEvery="{log_every}">
      <log idref="posterior"/>
      <log idref="likelihood"/>
      <log idref="prior"/>
    </logger>
    <logger id="treelog" fileName="$(filebase).trees" logEvery="{log_every}" mode="tree">
      <log id="TreeWithMetaDataLogger" spec="TreeWithMetaDataLogger" tree="@Tree"/>
    </logger>
  </run>
</beast>
"""
