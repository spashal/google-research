# coding=utf-8
# Copyright 2021 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Lint as: python3
"""This class provides shared utilities for parsing and writing SMU7 files."""

import collections
import csv
import enum
import itertools
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit import Geometry

from tensorflow.io import gfile

from smu import dataset_pb2

# The stage1 files do not label their error fields explicitly. This is the list
# of fields in order.
STAGE1_ERROR_FIELDS = [
    'error_nstat1', 'error_nstatc', 'error_nstatt', 'error_frequencies'
]

ATOM_CHARS = 'cnofh'

ATOM_TYPE_TO_MAX_BONDS = {
    dataset_pb2.BondTopology.AtomType.ATOM_C: 4,
    dataset_pb2.BondTopology.AtomType.ATOM_N: 3,
    dataset_pb2.BondTopology.AtomType.ATOM_NPOS: 4,
    dataset_pb2.BondTopology.AtomType.ATOM_O: 2,
    dataset_pb2.BondTopology.AtomType.ATOM_ONEG: 1,
    dataset_pb2.BondTopology.AtomType.ATOM_F: 1,
    dataset_pb2.BondTopology.AtomType.ATOM_H: 1
}

# The value is a pair of an atomic symbol and formal charge
ATOM_TYPE_TO_RDKIT = {
    dataset_pb2.BondTopology.AtomType.ATOM_C: ('C', 0),
    dataset_pb2.BondTopology.AtomType.ATOM_N: ('N', 0),
    dataset_pb2.BondTopology.AtomType.ATOM_NPOS: ('N', 1),
    dataset_pb2.BondTopology.AtomType.ATOM_O: ('O', 0),
    dataset_pb2.BondTopology.AtomType.ATOM_ONEG: ('O', -1),
    dataset_pb2.BondTopology.AtomType.ATOM_F: ('F', 0),
    dataset_pb2.BondTopology.AtomType.ATOM_H: ('H', 0),
}

ATOM_TYPE_TO_CHAR = {
    dataset_pb2.BondTopology.AtomType.ATOM_C: 'c',
    dataset_pb2.BondTopology.AtomType.ATOM_N: 'n',
    dataset_pb2.BondTopology.AtomType.ATOM_NPOS: 'n',
    dataset_pb2.BondTopology.AtomType.ATOM_O: 'o',
    dataset_pb2.BondTopology.AtomType.ATOM_ONEG: 'o',
    dataset_pb2.BondTopology.AtomType.ATOM_F: 'f',
    dataset_pb2.BondTopology.AtomType.ATOM_H: 'h'
}
ATOM_CHAR_TO_TYPE = {
    'c': dataset_pb2.BondTopology.AtomType.ATOM_C,
    'n': dataset_pb2.BondTopology.AtomType.ATOM_N,
    'o': dataset_pb2.BondTopology.AtomType.ATOM_O,
    'f': dataset_pb2.BondTopology.AtomType.ATOM_F,
    'h': dataset_pb2.BondTopology.AtomType.ATOM_H,
}
ATOM_CHAR_TO_ATOMIC_NUMBER = {
    'c': 6,
    'n': 7,
    'o': 8,
    'f': 9,
    'h': 1,
}

ATOM_TYPE_TO_ATOMIC_NUMBER = {
    dataset_pb2.BondTopology.AtomType.ATOM_C: 6,
    dataset_pb2.BondTopology.AtomType.ATOM_N: 7,
    dataset_pb2.BondTopology.AtomType.ATOM_NPOS: 7,
    dataset_pb2.BondTopology.AtomType.ATOM_O: 8,
    dataset_pb2.BondTopology.AtomType.ATOM_ONEG: 8,
    dataset_pb2.BondTopology.AtomType.ATOM_F: 9,
    dataset_pb2.BondTopology.AtomType.ATOM_H: 1
}

BOND_TYPE_TO_RDKIT = {
    dataset_pb2.BondTopology.BondType.BOND_SINGLE: Chem.rdchem.BondType.SINGLE,
    dataset_pb2.BondTopology.BondType.BOND_DOUBLE: Chem.rdchem.BondType.DOUBLE,
    dataset_pb2.BondTopology.BondType.BOND_TRIPLE: Chem.rdchem.BondType.TRIPLE,
}

INTEGER_TO_BOND_TYPE = [
    dataset_pb2.BondTopology.BondType.BOND_UNDEFINED,
    dataset_pb2.BondTopology.BondType.BOND_SINGLE,
    dataset_pb2.BondTopology.BondType.BOND_DOUBLE,
    dataset_pb2.BondTopology.BondType.BOND_TRIPLE,
]

ERROR_CODES = collections.OrderedDict([
    # TODO(pfr): give the ones with just error codes better names
    ('nstat1', 'error_nstat1'),
    ('nstatc', 'error_nstatc'),
    ('nstatv', 'error_frequencies'),
    ('nstatt', 'error_nstatt'),
    ('nsvato', 'error_atomic_analysis'),
    ('nsvnsb', 'error_nmr_analysis_b3lyp_small_basis'),
    ('nsvnlb', 'error_nmr_analysis_b3lyp_large_basis'),
    ('nsvele', 'error_charge_analysis'),
    ('nsvego', 'error_nsvego'),
    ('nsveh3', 'error_energies_orbitals_pvtz'),
    ('nsveh4', 'error_energies_orbitals_pvqz'),
    ('nsvec3', 'error_energies_orbitals_pcvtz'),
    ('nsvexc', 'error_excitation_energies'),
    ('nsveca', 'error_single_point_energies'),
    ('nsvmr1', 'error_inconsistent_molecule_energy_turbomole_mrcc'),
    ('nsvmr2', 'error_inconsistent_cation_energy_turbomole_mrcc'),
    ('nsvvib', 'error_normal_modes'),
    ('nsvor1', 'error_inconsistent_molecule_energy_turbomole_orca'),
    ('nsvor2', 'error_inconsistent_cation_energy_turbomole_orca'),
    ('nsvrot', 'error_rotational_modes'),
    ('nsvnsp', 'error_nmr_analysis_pbe0_small_basis'),
    ('nsvnlp', 'error_nmr_analysis_pbe0_large_basis'),
    ('nsvg09', 'error_nsvg09'),
    ('nsvho1', 'error_nsvho1'),
    ('nsvho2', 'error_nsvho2'),
    ('nsvho3', 'error_nsvho3'),
    ('nsvneg', 'error_nsvneg'),
])

# SMU1 was not included in our original bond topology enumeration. So we stick
# these bond topologies at the very end of the list. We also have to special
# case them in the parsing / writing. The tuples are:
# id provided in dat files, bond topology id we use, atom, valence
SPECIAL_ID_CASES = [
    (999999, 899649, 'F', 1),
    (999998, 899650, 'O', 2),
    (999997, 899651, 'N', 3),
    (999996, 899652, 'C', 4),
]

# Conversion constant from Bohr to Angstroms
BOHR_TO_ANGSTROMS = 0.529177249


def special_case_bt_id_from_dat_id(dat_id, smiles):
  """Determines if dat_id is a special case.

  Special case handling for SMU1. We see special cases in two ways.
  * If dat_id is 0 (happens in stage1 files), we use the smiles string to
    determine the bt_id
  * If dat_id is listed in SPECIAL_ID_CASES (happens in stage2 files), we use
    mapping from there

  Args:
    dat_id: integer id from the ID line of the .dat file
    smiles: smiles string for this case

  Returns:
    None if this is not a special case, bond topology id otherwise
  """
  if dat_id == 0:
    # Note that the smiles string for these special SMU1 cases is just the atom
    matched_ids = [vals[1] for vals in SPECIAL_ID_CASES if vals[2] == smiles]
    if matched_ids:
      return matched_ids[0]
    else:
      raise ValueError(f'ID from .dat is 0, but {smiles} is not a special case')
  else:
    matched_ids = [vals[1] for vals in SPECIAL_ID_CASES if vals[0] == dat_id]
    if matched_ids:
      return matched_ids[0]
  return None


def special_case_dat_id_from_bt_id(bt_id):
  """Determines if bt_id is a special case.

  Special case handling for SMU1.

  Args:
    bt_id: integer bond topology id

  Returns:
    None if this is not a special case, id to use for .dat file otherwise
  """
  matched_ids = [vals[0] for vals in SPECIAL_ID_CASES if vals[1] == bt_id]
  if matched_ids:
    return matched_ids[0]
  return None


def bohr_to_angstroms(length):
  """Convert bohr units to angstroms.

  Args:
    length: float

  Returns:
    float
  """
  return length * BOHR_TO_ANGSTROMS


def get_composition(topology):
  """Returns the composition/stoichiometry of the molecule.

  The composition is returned as a 'x{num heavy atoms}_' followed by a single
  character per atom type followed by the atom count for the respective type.
  Atoms appear in order 'cnohf'. Types
  with 0-count are omitted and 1 counts are omitted.
  Example: x07_c4o2fh7

  Args:
    topology: A BondTopology protocol buffer message.

  Returns:
    composition(string)
  """
  counts = {char: 0 for char in ATOM_CHARS}
  heavy_atom_count = 0
  for atom in topology.atoms:
    counts[ATOM_TYPE_TO_CHAR[atom]] += 1
    if atom != dataset_pb2.BondTopology.AtomType.ATOM_H:
      heavy_atom_count += 1
  components = []
  for c in ATOM_CHARS:
    if counts[c] == 0:
      continue
    elif counts[c] == 1:
      count_str = ''
    else:
      count_str = str(counts[c])
    components.append(c + count_str)
  return 'x{:02d}_{}'.format(heavy_atom_count, ''.join(components))


_STOICHIOMETRY_WITH_HYDROGENS_COMPONENTS = [
    'c', 'ch', 'ch2', 'ch3', 'ch4', 'n', 'nh', 'nh2', 'nh3', 'o', 'oh', 'oh2',
    'f', 'fh'
]


def get_canonical_stoichiometry_with_hydrogens(topology):
  """Get stoichiometry where hydrogen count is part of the atom type.

  Each heavy atom is typed by the number of hydrogens it's connected to, e.g.
  * c: carbon with no hydrogens
  * ch: carbon with one hydrogen
  * ch2: carbon with two hydrogens

  Each atom type is then included in the output with it's count of how often it
  occurs (just like a normal stoichiometry).

  Atom types are in order 'cnof' then by number of hydrogens

  For example
  * benzene: (ch)6
  * water: (oh2)   (note that the 1 is implicit)
  * ethylene: (ch2)2
  * acrylic acid: (c)(ch)(ch2)(o)(oh)

  Args:
    topology: A BondTopology protocol buffer message.

  Returns:
    string
  """
  hydrogen_counts = compute_bonded_hydrogens(topology,
                                             compute_adjacency_matrix(topology))
  components = collections.defaultdict(int)
  for atom_idx, h_count in enumerate(hydrogen_counts):
    this_component = ATOM_TYPE_TO_CHAR[topology.atoms[atom_idx]]
    if h_count >= 1:
      this_component += 'h'
      if h_count > 1:
        this_component += str(h_count)
    components[this_component] += 1

  out = ''
  for got_component in _STOICHIOMETRY_WITH_HYDROGENS_COMPONENTS:
    if got_component not in components:
      continue
    out += f'({got_component})'
    if components[got_component] > 1:
      out += str(components[got_component])

  return out


def compute_adjacency_matrix(topology):
  """Helper function to determine the adjacency matrix between heavy atoms.

  Only the upper diagonal of the matrix is filled, all other entries are 0.
  All values are non-negative, with positive values giving the bond order.

  Args:
    topology: A BondTopology protocol buffer message.

  Returns:
    An NxN matrix, where N equals the number of heavy atoms in a molecule.
  """
  side_length = len([
      atom for atom in topology.atoms
      if atom != dataset_pb2.BondTopology.AtomType.ATOM_H
  ])
  adjacency_matrix = [[0] * side_length for _ in range(side_length)]
  for bond in topology.bonds:
    if topology.atoms[bond.atom_a] == dataset_pb2.BondTopology.AtomType.ATOM_H:
      continue
    if topology.atoms[bond.atom_b] == dataset_pb2.BondTopology.AtomType.ATOM_H:
      continue
    if bond.bond_type == dataset_pb2.BondTopology.BondType.BOND_SINGLE:
      adjacency_matrix[bond.atom_a][bond.atom_b] = 1
      adjacency_matrix[bond.atom_b][bond.atom_a] = 1
    elif bond.bond_type == dataset_pb2.BondTopology.BondType.BOND_DOUBLE:
      adjacency_matrix[bond.atom_a][bond.atom_b] = 2
      adjacency_matrix[bond.atom_b][bond.atom_a] = 2
    elif bond.bond_type == dataset_pb2.BondTopology.BondType.BOND_TRIPLE:
      adjacency_matrix[bond.atom_a][bond.atom_b] = 3
      adjacency_matrix[bond.atom_b][bond.atom_a] = 3
  return adjacency_matrix


def compute_bonded_hydrogens(topology, adjacency_matrix):
  """Helper function to compute number of bonded hydrogens per heavy atom.

  Args:
    topology: A BondTopology protocol buffer message.
    adjacency_matrix: Matrix for all heavy atoms giving covalent bond orders.

  Returns:
    A list of integers (one per heavy atom) with bonded hydrogen counts.
  """
  side_length = len(adjacency_matrix)
  # Initialize with maximum number of hydrogens.
  # Only the first len(adjacency_matrix) atoms in the ordered topology are heavy
  # atoms capable of # binding protons.
  num_bonded_hydrogens = [
      ATOM_TYPE_TO_MAX_BONDS[atom] for atom in topology.atoms[:side_length]
  ]
  # Subtract paired bonds (to other heavy atoms).
  for i in range(side_length):
    for j in range(i + 1, side_length):
      num_bonded_hydrogens[i] -= adjacency_matrix[i][j]
      num_bonded_hydrogens[j] -= adjacency_matrix[i][j]
  return num_bonded_hydrogens


def labeled_smiles(mol):
  """Return the smiles for `mol` with atom numbers labeled.

  For each atom in `mol` set the atom map number to the
  atom number.
  CCC -> C[C:1][C:2]
  because atom map 0 is never displayed.

  Args:
    mol: a molecule.

  Returns:
    A labelled smiles string.
  """
  natoms = mol.GetNumAtoms()
  for i in range(1, natoms):
    mol.GetAtomWithIdx(i).SetAtomMapNum(i)

  to_be_returned: str = Chem.MolToSmiles(
      mol, kekuleSmiles=True, isomericSmiles=False)

  # Revert what we changed before returning.
  for i in range(1, natoms):
    mol.GetAtomWithIdx(i).SetAtomMapNum(0)

  return to_be_returned


def create_bond_topology(atoms, connectivity_matrix_string, hydrogens_string):
  """Creates a BondTopology from a compact string representation.

  Any hydrogens in the atoms string will be ignored. The appropriate number
  will be added based on what is in the hydrogens string.

  Args:
    atoms: a string like 'CCCCOON' (case insensitive) for the heavy atoms
    connectivity_matrix_string: a string for the uppertriangular connectivity
      matrix with bond orders, like '010210'
    hydrogens_string: a string for the number of hydrogens conencted to each
      heavy atom

  Returns:
    BondTopology
  """
  bond_topology = dataset_pb2.BondTopology()

  # Add the heavy atoms
  for atom_type in atoms.lower():
    if atom_type == 'h':
      continue
    try:
      bond_topology.atoms.append(ATOM_CHAR_TO_TYPE[atom_type])
    except KeyError:
      raise ValueError('Unknown atom type: {}'.format(atom_type))

  num_heavy_atoms = len(bond_topology.atoms)

  # Now add the bonds between the heavy atoms
  if num_heavy_atoms > 1:
    for (i, j), bond_order in zip(
        np.nditer(np.triu_indices(num_heavy_atoms, k=1)),
        connectivity_matrix_string):
      if bond_order == '0':
        continue
      bond = bond_topology.bonds.add()
      bond.atom_a = int(i)
      bond.atom_b = int(j)
      if bond_order == '1':
        bond.bond_type = dataset_pb2.BondTopology.BondType.BOND_SINGLE
      elif bond_order == '2':
        bond.bond_type = dataset_pb2.BondTopology.BondType.BOND_DOUBLE
      elif bond_order == '3':
        bond.bond_type = dataset_pb2.BondTopology.BondType.BOND_TRIPLE
      else:
        raise ValueError('Bad bond order {}'.format(bond_order))

  # Now add the hydrogens, and adjust charged atoms if the total bond counts
  # indicate that.
  expected_hydrogens = compute_bonded_hydrogens(
      bond_topology, compute_adjacency_matrix(bond_topology))
  for atom_idx, (actual_h, expected_h) in enumerate(
      zip(hydrogens_string, expected_hydrogens)):
    actual_h = int(actual_h)
    diff = expected_h - actual_h
    atom_type = bond_topology.atoms[atom_idx]
    if diff == -1 and atom_type == dataset_pb2.BondTopology.AtomType.ATOM_N:
      bond_topology.atoms[
          atom_idx] = dataset_pb2.BondTopology.AtomType.ATOM_NPOS
    elif diff == 1 and atom_type == dataset_pb2.BondTopology.AtomType.ATOM_O:
      bond_topology.atoms[
          atom_idx] = dataset_pb2.BondTopology.AtomType.ATOM_ONEG
    elif diff:
      raise ValueError(
          f'Bad hydrogen count (actual={actual_h}, expected={expected_h} '
          f'for {atom_type}, index {atom_idx}')
    for _ in range(actual_h):
      bond_topology.atoms.append(dataset_pb2.BondTopology.AtomType.ATOM_H)
      h_idx = len(bond_topology.atoms) - 1
      bond = bond_topology.bonds.add()
      bond.atom_a = atom_idx
      bond.atom_b = h_idx
      bond.bond_type = dataset_pb2.BondTopology.BondType.BOND_SINGLE

  return bond_topology


def parse_bond_topology_line(line):
  """Parses the a line from the enumeration of bond topologies.

  These files are generated by a fortran program that uses fixed width
  formatting that varies by topology size.

  Args:
    line: string

  Returns:
    num atoms (int),
    atoms str (like 'N+O O O-')
    connectivity matrix str (e.g. '010110')
    hydrogen count str (e.g. '3000')
  """
  line = line.rstrip()
  num_atoms = int(line[0:2])
  atoms_end = 4 + 2 * num_atoms
  connectivity_end = atoms_end + 2 + num_atoms * (num_atoms - 1) // 2
  if len(line) != connectivity_end + 2 + num_atoms:
    raise ValueError('Wrong line length: "{}"'.format(line))
  return (num_atoms, line[4:atoms_end], line[atoms_end + 2:connectivity_end],
          line[connectivity_end + 2:connectivity_end + 2 + num_atoms])


def generate_bond_topologies_from_csv(filename):
  """Generator for bond topologies stored in a csv.

  See merge_bond_topologies.py for the expected format.

  Args:
    filename: input csv

  Yields:
    BondTopology
  """
  with gfile.GFile(filename, 'r') as infile:
    reader = csv.reader(iter(infile))
    next(reader)  # skip the header line
    for row in reader:
      bt_id, _, atoms, connectivity, hydrogens, smiles = row
      # The atoms strings looks like 'C N N+O O-' where every atom has a space,
      # +, or - after it. create_bond_topology doesn't want the charge markings
      # (just a string like 'CNNOO') so the [::2] skips those.
      bond_topology = create_bond_topology(atoms[::2], connectivity, hydrogens)
      bond_topology.smiles = smiles
      bond_topology.bond_topology_id = int(bt_id)
      yield bond_topology


def parse_duplicates_file(filename):
  """Parses duplciate file into a pandas dataframe.

  The duplciate file supplied by our collaborators (called
  list.equivalent_{isomers,conformers.dat) is a two column, space separated
  file of composite names like x07_n4o3h4.091404.073
  which we parse the names into columns
  * nameX: original composiite name from file
  * stoichX: string for the stoichiometry
  * btidX: bond topology id
  * shortconfidX: 3 digit conformer id
  * confidX: full conformer id that we use (btid * 1000 + shortconfid)
  (for X = 1 or 2)

  Args:
    filename: file to read (usually list.equivalent_isomers.dat)

  Returns:
    pd.DataFrame
  """
  with gfile.GFile(filename) as f:
    df_dups = pd.read_csv(
        f, delim_whitespace=True, names=['name1', 'name2'], header=None)

  for idx in ['1', '2']:
    df_dups = pd.concat([
        df_dups,
        df_dups['name' +
                idx].str.extract(r'x07_([\w\d]+)\.(\d+).(\d+)').rename(columns={
                    0: 'stoich' + idx,
                    1: 'btid' + idx,
                    2: 'shortconfid' + idx
                })
    ],
                        axis=1)
    df_dups['btid' + idx] = df_dups['btid' + idx].astype(int)
    df_dups['shortconfid' + idx] = df_dups['shortconfid' + idx].astype(int)
    df_dups['confid' + idx] = (
        df_dups['btid' + idx] * 1000 + df_dups['shortconfid' + idx])

  return df_dups


def bond_topology_to_molecule(bond_topology):
  """Converts a bond topology proto to an RDKit molecule.

  Args:
    bond_topology: dataset_pb2.BondTopology

  Returns:
    rdkit.Chem.rdchem.RWMol
  """
  mol = Chem.rdchem.RWMol()
  for pb_atom_idx, pb_atom in enumerate(bond_topology.atoms):
    symbol, charge = ATOM_TYPE_TO_RDKIT[pb_atom]
    atom = Chem.Atom(symbol)
    atom.SetFormalCharge(charge)
    atom_idx = mol.AddAtom(atom)
    assert atom_idx == pb_atom_idx

  for pb_bond in bond_topology.bonds:
    mol.AddBond(pb_bond.atom_a, pb_bond.atom_b,
                BOND_TYPE_TO_RDKIT[pb_bond.bond_type])

  return mol


def conformer_to_molecules(conformer,
                           include_initial_geometries=True,
                           include_optimized_geometry=True,
                           include_all_bond_topologies=True):
  """Converts a Conformer to RDKit molecules.

  Because a Conformer can include multiple bond topologies and geometries,
  multiple RDKit molecule objects can be produced

  The name of the molcule will be (all on one line)
  SMU <confid>
  bt=<bt_id>(<bt_idx>/<bt_count>)
  geom=[opt|init(<init_idx>/<init_count>)]
  where
    confid: conformer_id
    bt_id: bond_topology_id
    bt_idx: index in bond_topologies
    bt_count: size of bond_topologies
    init_idx: index in initial_geometries
    init_count: size of initial_geometries

  Args:
    conformer: dataset_pb2.Conformer
    include_initial_geometries: output molecule for each initial_geometries
    include_optimized_geometry: output molecule for optimized_geometry
    include_all_bond_topologies: if False, use only the first entry of
      bond_topologies. If True, output molecule for each bond_topologies.

  Yields:
    rdkit.Chem.rdchem.RWMol
  """
  bt_count = len(conformer.bond_topologies)
  if include_all_bond_topologies:
    bts = conformer.bond_topologies
  else:
    bts = conformer.bond_topologies[0:1]
  requested_bond_topologies = [(bt, f'{bt.bond_topology_id}({i}/{bt_count})')
                               for i, bt in enumerate(bts, start=1)]

  # requested_geometries will be a list of tuples of
  # (goemetry, label)
  # where label is a string describing the geometry
  requested_geometries = []
  if include_initial_geometries:
    init_count = len(conformer.initial_geometries)
    requested_geometries.extend([
        (geom, f'init({i}/{init_count})')
        for i, geom in enumerate(conformer.initial_geometries)
    ])
  if include_optimized_geometry:
    requested_geometries.append((conformer.optimized_geometry, 'opt'))

  for bt, bt_label in requested_bond_topologies:
    for geom, geom_label in requested_geometries:

      mol = bond_topology_to_molecule(bt)
      mol.SetProp(
          '_Name',
          f'SMU {conformer.conformer_id} bt={bt_label} geom={geom_label} fate={conformer.fate}'
      )

      # Add in the coordinates
      conf = Chem.Conformer(len(bt.atoms))
      conf.Set3D(True)
      for atom_idx, pos in enumerate(geom.atom_positions):
        conf.SetAtomPosition(
            atom_idx,
            Geometry.Point3D(
                bohr_to_angstroms(pos.x), bohr_to_angstroms(pos.y),
                bohr_to_angstroms(pos.z)))
      mol.AddConformer(conf)

      # TODO(pfr): put the computed properties as properties of the molecule.

      yield mol


def compute_smiles_for_bond_topology(bond_topology,
                                     include_hs,
                                     labeled_atoms=False):
  """Calculate a canonical smiles for the given bond_topology.

  The bond topology may have the smiles field filled in but this method ignores
  that and calculates it directly from the atom and bond description.

  Args:
    bond_topology: dataset_pb2.BondTopology
    include_hs: whether to include hs in the smiles string
    labeled_atoms: whether or not to apply atom number labels.

  Returns:
    string
  """
  return compute_smiles_for_molecule(
      bond_topology_to_molecule(bond_topology),
      include_hs,
      labeled_atoms=labeled_atoms)


def compute_smiles_for_molecule(mol, include_hs, labeled_atoms=False):
  """Calculate a canonical smiles for the given RDKit Molecule.

  Note that you probably should NOT have sanitized your RDKit molecule. The
  sanitization procedure can move bonds around in funny ways where here we are
  ignoring aromaticity and keeping bond orders fixed. Because we have such
  funny molecules here, RDKit sometimes does things we don't expect during
  sanitization.

  This is *almost* what RDKit does by default, but because we don't want to
  deal with aromaticity at all, we can't sanitize. That produces one case
  where RDKit will produce different SMILES for what is the same molecule.
  We catch that one case here.

  Note that it is the caller's responsibility to make sure that any Hs intended
  are in the mol. They will NOT be added by this function even when include_hs
  is given.

  If labeled_atoms is True, a smiles where every atom has as its atom map number
  the atom number within the molecule.

  Args:
    mol: rdkit Mol
    include_hs: whether to include hs in the smiles string
    labeled_atoms: whether or not to apply atom number labels.

  Returns:
    string
  """
  if not include_hs:
    mol = Chem.RemoveHs(mol, sanitize=False)
  if labeled_atoms:
    return labeled_smiles(mol)
  smiles = Chem.MolToSmiles(mol, kekuleSmiles=True, isomericSmiles=False)
  # Yep, this is weird. Depending on the order of the atoms presented to RDKit
  # you can get either of these two smiles back. We arbitrarily picked one of
  # them to return. Note that this one case has no hydrogens so it doesn't
  # matter whether include_hs is True
  if smiles == 'C12=C3C4=C1C4=C23':
    return 'C12=C3C1=C1C2=C31'
  return smiles


class SmilesCompareResult(enum.Enum):
  MISSING = 2
  MISMATCH = 3
  MATCH = 4

  def __str__(self):
    out = super(SmilesCompareResult, self).__str__()
    # remove the SmilesCompareResult. part
    return out[20:]


def bond_topology_smiles_comparison(bond_topology):
  """Compares the given smiles string to one generated by RDKit.

  The atom/bond structure defines a molecule that we can then turn into a
  SMILES string. There is also a smiles string in the bond topology that was
  generated by large computational pipeline and may have some issues.

  There are three output states. The first applicable one is returned.
  * MISSING: bond_topology does not have a smiles field
  * MISMATCH: bond_topology.smiles does not match the one generated by RDKit
  * MATCH: bond_topology.smiles matches one from RDKit

  Args:
    bond_topology: dataset_pb2.BondTopology

  Returns:
    SmilesCompareResult, SMILES(with H), SMILES(without H)
  """
  smiles_with_h = compute_smiles_for_bond_topology(
      bond_topology, include_hs=True)
  smiles_without_h = compute_smiles_for_bond_topology(
      bond_topology, include_hs=False)

  if not bond_topology.smiles:
    return SmilesCompareResult.MISSING, smiles_with_h, smiles_without_h

  if bond_topology.smiles == smiles_without_h:
    return SmilesCompareResult.MATCH, smiles_with_h, smiles_without_h
  else:
    return SmilesCompareResult.MISMATCH, smiles_with_h, smiles_without_h


class _ConformerSource(enum.Enum):
  DUPLICATE = 0
  STAGE1 = 1
  STAGE2 = 2


def _conformer_source(conf):
  """Determines source of given conformer."""
  if not conf.HasField('properties'):
    if conf.duplicated_by == 0 and not conf.duplicate_of:
      raise ValueError(
          'Unknown conformer source, no properties or duplicates: ' + str(conf))
    return _ConformerSource.DUPLICATE
  # Kind of a dumb hack, but the easiest thing to look for to distinguish stage1
  # and stage 2 is that stage 1 only has timings for two computation steps.
  if len(conf.properties.calculation_statistics) == 2:
    return _ConformerSource.STAGE1
  return _ConformerSource.STAGE2


# A list of fields that will be returned by merge_conformer on a conflict.
# The fields for the STAGE1 conformer are first, then fields for the STAGE2
# conformer.
MERGE_CONFLICT_FIELDS = [
    'conformer_id',
    'error_nstat1',
    'error_nstatc',
    'error_nstatv',
    'error_nstatt',
    'initial_geometry_energy_1',
    'initial_geometry_gradient_norm_1',
    'optimized_geometry_energy_1',
    'optimized_geometry_gradient_norm_1',
    'has_initial_geometry_1',
    'has_optimized_geometry_1',
    'initial_geometry_energy_2',
    'initial_geometry_gradient_norm_2',
    'optimized_geometry_energy_2',
    'optimized_geometry_gradient_norm_2',
    'has_initial_geometry_2',
    'has_optimized_geometry_2',
]


def merge_conformer(conf1, conf2):
  """Tries to merge information from two conformers.

  During the pipeline, we have partial information about conformers that we
  need to merge. This is the workhorse function for merging these.

  Only conformers with the same conformer_id should be merged.

  The key concept is to identify a source of each conformer:
  * STAGE2: From end of pipeline, with mostly complete info
  * STAGE1: From after geometry optimization. Except for duplicate information
    which may have been merged, mostly contains duplicate information to
    STAGE2. However, in some cases it's expected that stage2 will differ
    because of reruns in STAGE2.
  * DUPLICATE: An almost bare conformer with just duplicated_by and/or
    duplicate_of fields

  May modify one of the inputs.

  Note that this is not the most general merge that the format suggests. In
  particular, it's expected that there is at most 1 initial_geometries and
  1 bond_topologies (and it's the same for all conformers). The final data won't
  be like this but it handles what's in the pipeline at this point we use this.

  While merging STAGE1 and STAGE2, conflicting values of some fields may be
  detected. If they are, then a list of all fields (from MERGE_CONFLICT_FIELDS)
  are returned in addition to doing the merge. If there is no conflict, None
  is returned as the second argument.

  ValueError is returned when a different error besides these expected
  differences is found.

  Args:
    conf1: dataset_pb2.Conformer
    conf2: dataset_pb2.Conformer

  Returns:
    dataset_pb2.Conformer, None or list of field values (see above)

  Raises:
    ValueError: if len(initial_geometries) != 1, len(bond_topologies) != 1,
      bond_topologies differ, or incompatible duplicated_by fields
  """
  source1 = _conformer_source(conf1)
  source2 = _conformer_source(conf2)

  if source1 == source2:
    if source1 == _ConformerSource.STAGE1 or source1 == _ConformerSource.STAGE2:
      raise ValueError(
          'Can not merge two conformers of source {}'.format(source1))
    conf1.MergeFrom(conf2)
    return conf1, None

  if source2.value < source1.value:
    conf1, conf2 = conf2, conf1
    source1, source2 = source2, source1

  if len(conf1.initial_geometries) > 1:
    raise ValueError('At most 1 initial_geometries allowed, got {}'.format(
        len(conf1.initial_geometries)))
  if len(conf2.initial_geometries) > 1:
    raise ValueError('At most 1 initial_geometries allowed, got {}'.format(
        len(conf2.initial_geometries)))

  if len(conf1.bond_topologies) > 1:
    raise ValueError('At most 1 bond_topologies allowed, got {}'.format(
        len(conf1.initial_geometries)))
  if len(conf2.bond_topologies) > 1:
    raise ValueError('At most 1 bond_topologies allowed, got {}'.format(
        len(conf2.initial_geometries)))

  if conf1.bond_topologies and conf2.bond_topologies:
    if conf1.bond_topologies[0] != conf2.bond_topologies[0]:
      raise ValueError(
          'All bond topologies must be the same, got ids {} and {}'.format(
              conf1.bond_topologies[0].bond_topology_id,
              conf2.bond_topologies[0].bond_topology_id))

  # We set the conflict info here because we'll be messing around with fields
  # below. We may not need this if we don't actually find a conflict.
  conflict_info = [conf1.conformer_id]
  conflict_info.append(conf1.properties.errors.error_nstat1)
  conflict_info.append(conf1.properties.errors.error_nstatc)
  conflict_info.append(conf1.properties.errors.error_frequencies)  # nstatv
  conflict_info.append(conf1.properties.errors.error_nstatt)
  for c in [conf1, conf2]:
    conflict_info.append(c.properties.initial_geometry_energy.value)
    conflict_info.append(c.properties.initial_geometry_gradient_norm.value)
    conflict_info.append(c.properties.optimized_geometry_energy.value)
    conflict_info.append(c.properties.optimized_geometry_gradient_norm.value)
    conflict_info.append(bool(c.initial_geometries))
    conflict_info.append(c.HasField('optimized_geometry'))

  # The stage1 (in source1) and stage2 (in source2) is the only non-trivial
  # merge. We look for conflicts between them and then a few special cases.
  has_conflict = False
  if source1 == _ConformerSource.STAGE1 and source2 == _ConformerSource.STAGE2:
    if len(conf1.bond_topologies) != 1 or len(conf2.bond_topologies) != 1:
      has_conflict = True

    if len(conf1.initial_geometries) != len(conf2.initial_geometries):
      has_conflict = True
    if (conf1.HasField('optimized_geometry') !=
        conf2.HasField('optimized_geometry')):
      has_conflict = True

    for field in STAGE1_ERROR_FIELDS:
      # Only stage1 uses these old style error fields, so we just copy them
      # over
      setattr(conf2.properties.errors, field,
              getattr(conf1.properties.errors, field))

    for field, atol in [
        ('initial_geometry_energy', 2e-6),
        ('initial_geometry_gradient_norm', 1e-6),
        ('optimized_geometry_energy', 2e-6),
        ('optimized_geometry_gradient_norm', 1e-6),
    ]:
      val1 = getattr(conf1.properties, field).value
      val2 = getattr(conf2.properties, field).value
      # In some cases, stage2 files have -1 for these fields where stage1
      # doesn't. At some point, stricter error checking was done such that
      # nonsense values were not put into the .dat. So if stage2 has a -1, we
      # just leave it.
      if val2 != -1.0:
        if not np.isclose(val1, val2, atol=atol, rtol=0):
          has_conflict = True

    # This isn't actually a conflict per-se, but we want to find anything that
    # is not an allowed set of combinations of error values.
    error_codes = (conf1.properties.errors.error_nstat1,
                   conf1.properties.errors.error_nstatc,
                   conf1.properties.errors.error_frequencies,
                   conf1.properties.errors.error_nstatt)
    if conf1.properties.errors.error_frequencies == 101:
      # This happens for exactly one molecule. If anything else shows up
      # here we will mark it as a conflict so it comes out in that output
      if conf2.conformer_id != 795795001:
        has_conflict = True
    elif error_codes not in [(1, 1, 1, 1), (3, 1, 1, 1), (2, 3, 2, 1),
                             (5, 1, 3, 1), (1, 1, 101, 1)]:
      has_conflict = True

    # After all of that, we always take the stage1 initial energy,
    # gradient norm, and positions.
    conf2.properties.initial_geometry_energy.value = (
        conf1.properties.initial_geometry_energy.value)
    conf2.properties.initial_geometry_gradient_norm.value = (
        conf1.properties.initial_geometry_gradient_norm.value)
    conf2.initial_geometries[0].CopyFrom(conf1.initial_geometries[0])

    # The 800 and 700 are special cases where we want to take the stage1 data
    if (conf2.properties.errors.status == 800 or
        conf2.properties.errors.status == 700):
      # Flip back because we will base everything on the stage1 file
      conf1, conf2 = conf2, conf1
      source1, source2 = source2, source1

      conf2.properties.errors.status = (500 +
                                        conf1.properties.errors.status // 10)
      conf2.which_database = dataset_pb2.COMPLETE
      if np.any(np.asarray(conf2.properties.harmonic_frequencies.value) < -30):
        conf2.properties.errors.warn_vib_imaginary = 2
      elif np.any(np.asarray(conf2.properties.harmonic_frequencies.value) < 0):
        conf2.properties.errors.warn_vib_imaginary = 1

  # Move over all duplicate info.
  if (conf1.duplicated_by != 0 and conf2.duplicated_by != 0 and
      conf1.duplicated_by != conf2.duplicated_by):
    raise ValueError('Incompatible duplicated_by {} {}'.format(
        conf1.duplicated_by, conf2.duplicated_by))
  # max is just to get the non-zero one
  conf2.duplicated_by = max(conf1.duplicated_by, conf2.duplicated_by)
  conf2.duplicate_of.extend(conf1.duplicate_of)

  if not has_conflict:
    return conf2, None

  return conf2, conflict_info


def conformer_calculation_error_level(conformer):
  """Returns whether status codes indicate this conformer had serious errors.

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    integer, higher values are more srious errors
      5: serious problems
      4: major problems
      3: moderate problems
      2: minor problems, serious warning
      1: minor problems, vibrational analysis warning
      0: minor or no problem
  """
  source = _conformer_source(conformer)
  errors = conformer.properties.errors

  # The levels aren't very well defined for STAGE1.
  # We'll call all errors serious
  if source == _ConformerSource.STAGE1:
    if errors.error_nstat1 != 1 and errors.error_nstat1 != 3:
      return 5

    if (errors.error_nstatc != 1 or errors.error_nstatt != 1 or
        errors.error_frequencies != 1):
      return 5

    return 0

  # Now logic for stage2 files.
  if errors.status >= 64:
    return 5
  elif errors.status >= 8:
    return 4
  elif errors.status >= 4:
    return 3

  # This is warning level 'C' from Bazel documentation.
  if (errors.warn_t1 > 1 or errors.warn_t1_excess > 1 or
      errors.warn_bse_b5_b6 > 1 or errors.warn_bse_cccsd_b5 > 1 or
      errors.warn_exc_lowest_excitation > 1 or
      errors.warn_exc_smallest_oscillator > 0 or
      errors.warn_exc_largest_oscillator > 0):
    return 2

  # This is warning level 'B" from Bazel documentation.
  if (errors.warn_vib_linearity > 0 or errors.warn_vib_imaginary > 1):
    return 1

  return 0


def filter_conformer_by_availability(conformer, allowed):
  """Filters fields of Conformer by availability annotations.

  *Modifies* the input conformer.

  Args:
    conformer: dataset_pb2.Conformer
    allowed: list of AvailabilityEnum
  """
  # A bit of a hack because original_conformer_index is the only field we
  # filter in the conformer not in the properties subfield.
  if dataset_pb2.INTERNAL_ONLY not in allowed:
    conformer.ClearField('original_conformer_index')
  for descriptor, _ in conformer.properties.ListFields():
    if (descriptor.GetOptions().Extensions[dataset_pb2.availability]
        not in allowed):
      conformer.properties.ClearField(descriptor.name)


def should_include_in_standard(conformer):
  """Returns whether this conformer should be included in the Standard form.

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    boolean
  """
  if conformer.duplicated_by > 0:
    return False
  if conformer.which_database == dataset_pb2.COMPLETE:
    return False
  elif conformer.which_database == dataset_pb2.STANDARD:
    return True
  else:
    # This should only happen with stage1 only files.
    if conformer_calculation_error_level(conformer) > 0:
      return False
    else:
      return True


def conformer_to_standard(conformer):
  """Converts a Conformer from internal to 'Standard' form.

  The "Complete" dataset has all information that anyone could reasonably use.
  The "Standard" dataset is a reduced form with information that we trust and
  various simplifications.

  *Modifies* the input conformer.

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    dataset_pb2.Conformer or None (meaning that this conformer should be
      filtered)
  """
  if not should_include_in_standard(conformer):
    return None

  filter_conformer_by_availability(conformer, [dataset_pb2.STANDARD])

  return conformer


def clean_up_error_codes(conformer):
  """Cleans up error codes for the final dataset.

  Two major types of thigns need to be changed.
  * For stage1 only conformers, the new status code needs to be set
  * For stage2 conformers, the old style error codes need to be cleared.

  Modifies the input conformer

  Args:
    conformer: dataset_pb2.Conformer
  """
  source = _conformer_source(conformer)
  if source == _ConformerSource.STAGE1:
    if conformer.properties.errors.status:
      # This is a special case where the stage1 conformer was already put
      # together as a final entry during the merging process. Everything
      # has already been set up.
      pass
    elif (conformer.properties.errors.error_nstat1 == 1 or
          conformer.properties.errors.error_nstat1 == 3):
      # This should be a duplciate. If we have no record of a dup, we'll
      # leaves is as stauts 0 and let it be caught by fate below
      if conformer.duplicated_by:
        conformer.properties.errors.status = -1
    elif conformer.properties.errors.error_nstat1 == 5:
      # optimization was successful, but optimized to different topology
      conformer.properties.errors.status = 590
    elif conformer.properties.errors.error_nstat1 == 2:
      # optimization failed. Clean up the error codes and remove some info
      conformer.properties.errors.status = 600
      conformer.properties.ClearField('initial_geometry_energy')
      conformer.properties.ClearField('initial_geometry_gradient_norm')
      conformer.properties.ClearField('optimized_geometry_energy')
      conformer.properties.ClearField('optimized_geometry_gradient_norm')
      conformer.ClearField('optimized_geometry')

    # If something isn't caught there, we'll let it go through with
    # status still unset. This will be categorized later in determine_fate
  elif source == _ConformerSource.STAGE2:
    pass
  else:
    raise ValueError(
        f'Clean up can only handle Stage1 or 2 conformers, got {conformer}')

  for field in STAGE1_ERROR_FIELDS:
    conformer.properties.errors.ClearField(field)


_SENTINEL_VALUE_FIELDS = [
    'initial_geometry_energy',
    'initial_geometry_gradient_norm',
    'optimized_geometry_energy',
    'optimized_geometry_gradient_norm',
]


def clean_up_sentinel_values(conformer):
  """Removes some snetinel values, relying on empty protobuf fields to indicate absence.

  Modifies the conformer

  Args:
    conformer: dataset_pb2.Conformer
  """
  for field in _SENTINEL_VALUE_FIELDS:
    if getattr(conformer.properties, field).value == -1.0:
      conformer.properties.ClearField(field)


_ZERO_FIELD_CHECK_SCALAR = [
    'single_point_energy_atomic_b5',
    'single_point_energy_atomic_b6',
    'single_point_energy_b3lyp_6_31ppgdp',
    'single_point_energy_b3lyp_aug_pcs_1',
    'single_point_energy_cc2_tzvp',
    'single_point_energy_ccsd_2sd',
    'single_point_energy_ccsd_2sp',
    'single_point_energy_ccsd_3psd',
    'single_point_energy_ccsd_t_2sd',
    'single_point_energy_ccsd_t_2sp',
    'single_point_energy_eccsd',
    'single_point_energy_hf_2sd',
    'single_point_energy_hf_2sp',
    'single_point_energy_hf_3',
    'single_point_energy_hf_34',
    'single_point_energy_hf_3psd',
    'single_point_energy_hf_4',
    'single_point_energy_hf_6_31gd',
    'single_point_energy_hf_cvtz',
    'single_point_energy_hf_tzvp',
    'single_point_energy_mp2_2sd',
    'single_point_energy_mp2_2sp',
    'single_point_energy_mp2_3',
    'single_point_energy_mp2_34',
    'single_point_energy_mp2_3psd',
    'single_point_energy_mp2_4',
    'single_point_energy_mp2_tzvp',
    'single_point_energy_mp2ful_cvtz',
    'single_point_energy_pbe0_6_311gd',
    'single_point_energy_pbe0_6_311gd_cat',
    'single_point_energy_pbe0_6_311gd_cat_mrcc',
    'single_point_energy_pbe0_6_311gd_cat_orca',
    'single_point_energy_pbe0_6_311gd_mrcc',
    'single_point_energy_pbe0_6_311gd_orca',
    'single_point_energy_pbe0_6_31ppgdp',
    'single_point_energy_pbe0_aug_pc_1',
    'single_point_energy_pbe0_aug_pcs_1',
    'single_point_energy_pbe0d3_6_311gd',
    'homo_b3lyp_6_31ppgdp',
    'homo_b3lyp_aug_pcs_1',
    'homo_hf_3',
    'homo_hf_4',
    'homo_hf_6_31gd',
    'homo_hf_cvtz',
    'homo_hf_tzvp',
    'homo_pbe0_6_311gd',
    'homo_pbe0_6_31ppgdp',
    'homo_pbe0_aug_pc_1',
    'homo_pbe0_aug_pcs_1',
    'lumo_b3lyp_6_31ppgdp',
    'lumo_b3lyp_aug_pcs_1',
    'lumo_hf_3',
    'lumo_hf_4',
    'lumo_hf_6_31gd',
    'lumo_hf_cvtz',
    'lumo_hf_tzvp',
    'lumo_pbe0_6_311gd',
    'lumo_pbe0_6_31ppgdp',
    'lumo_pbe0_aug_pc_1',
    'lumo_pbe0_aug_pcs_1',
    'atomization_energy_excluding_zpe_atomic_b5',
    'atomization_energy_excluding_zpe_atomic_b5_um',
    'atomization_energy_excluding_zpe_atomic_b6',
    'atomization_energy_excluding_zpe_atomic_b6_um',
    'atomization_energy_excluding_zpe_eccsd',
    'atomization_energy_excluding_zpe_eccsd_um',
    'atomization_energy_including_zpe_atomic_b5',
    'atomization_energy_including_zpe_atomic_b5_um',
    'atomization_energy_including_zpe_atomic_b6',
    'atomization_energy_including_zpe_atomic_b6_um',
    'atomization_energy_including_zpe_eccsd',
    'atomization_energy_including_zpe_eccsd_um',
    'enthalpy_of_formation_0k_atomic_b5',
    'enthalpy_of_formation_0k_atomic_b5_um',
    'enthalpy_of_formation_0k_atomic_b6',
    'enthalpy_of_formation_0k_atomic_b6_um',
    'enthalpy_of_formation_0k_eccsd',
    'enthalpy_of_formation_0k_eccsd_um',
    'enthalpy_of_formation_298k_atomic_b5',
    'enthalpy_of_formation_298k_atomic_b5_um',
    'enthalpy_of_formation_298k_atomic_b6',
    'enthalpy_of_formation_298k_atomic_b6_um',
    'enthalpy_of_formation_298k_eccsd',
    'enthalpy_of_formation_298k_eccsd_um',
]

_ZERO_FIELD_CHECK_ATOMIC = [
    'nmr_isotropic_shielding_b3lyp_6_31ppgdp',
    'nmr_isotropic_shielding_b3lyp_aug_pcs_1',
    'nmr_isotropic_shielding_pbe0_6_31ppgdp',
    'nmr_isotropic_shielding_pbe0_aug_pcs_1',
    'partial_charges_esp_fit_hf_6_31gd',
    'partial_charges_esp_fit_pbe0_aug_pc_1',
    'partial_charges_loewdin_hf_6_31gd',
    'partial_charges_loewdin_pbe0_aug_pc_1',
    'partial_charges_mulliken_hf_6_31gd',
    'partial_charges_mulliken_pbe0_aug_pc_1',
    'partial_charges_natural_nbo_hf_6_31gd',
    'partial_charges_natural_nbo_pbe0_aug_pc_1',
    'partial_charges_paboon_hf_6_31gd',
    'partial_charges_paboon_pbe0_aug_pc_1',
]


def find_zero_values(conformer):
  """Finds fields whose values are exactly 0.

  Fields that are exactly zero are likely to be problematic in some way so we
  look for
  a handful of these.

  Args:
    conformer: dataset_pb2.Conformer

  Yields:
    string of field name
  """
  properties = conformer.properties

  # excitation is different because it's a MultiScalar
  if properties.HasField('excitation_energies_cc2'):
    for value in properties.excitation_energies_cc2.value:
      if value == 0.0:
        yield 'excitation_energies_cc2'

  for field in _ZERO_FIELD_CHECK_SCALAR:
    if properties.HasField(field) and getattr(properties, field).value == 0.0:
      yield field

  for field in _ZERO_FIELD_CHECK_ATOMIC:
    if properties.HasField(field):
      for value in getattr(properties, field).values:
        if value == 0.0:
          yield field


def determine_fate(conformer):
  """Determines the cateogrical FateCategory for conformer.

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    dataset_pb2.Conformer.FateCategory
  """
  source = _conformer_source(conformer)
  if source == _ConformerSource.DUPLICATE:
    # This shouldn't really happen in the real set so we'll just leave it as
    # undefined.
    return dataset_pb2.Conformer.FATE_UNDEFINED

  elif source == _ConformerSource.STAGE1:
    if conformer.duplicated_by > 0:
      this_btid = conformer.conformer_id // 1000
      other_btid = conformer.duplicated_by // 1000
      if this_btid == other_btid:
        return dataset_pb2.Conformer.FATE_DUPLICATE_SAME_TOPOLOGY
      else:
        return dataset_pb2.Conformer.FATE_DUPLICATE_DIFFERENT_TOPOLOGY

    status = conformer.properties.errors.status
    if status == 600:
      return dataset_pb2.Conformer.FATE_GEOMETRY_OPTIMIZATION_PROBLEM
    elif status == 590:
      return dataset_pb2.Conformer.FATE_DISASSOCIATED
    elif status == 570 or status == 580:
      return dataset_pb2.Conformer.FATE_DISCARDED_OTHER
    else:
      # This means that we can find no reason this shouldn't have gone on to
      # stage2.
      return dataset_pb2.Conformer.FATE_NO_CALCULATION_RESULTS

  elif source == _ConformerSource.STAGE2:
    error_level = conformer_calculation_error_level(conformer)
    if error_level == 5:
      return dataset_pb2.Conformer.FATE_CALCULATION_WITH_SERIOUS_ERROR
    elif error_level == 4:
      return dataset_pb2.Conformer.FATE_CALCULATION_WITH_MAJOR_ERROR
    elif error_level == 3:
      return dataset_pb2.Conformer.FATE_CALCULATION_WITH_MODERATE_ERROR
    elif error_level == 2:
      return dataset_pb2.Conformer.FATE_CALCULATION_WITH_WARNING_SERIOUS
    elif error_level == 1:
      return dataset_pb2.Conformer.FATE_CALCULATION_WITH_WARNING_VIBRATIONAL
    elif error_level == 0:
      return dataset_pb2.Conformer.FATE_SUCCESS
    else:
      raise ValueError(f'Bad error_level {error_level}')

  else:
    raise ValueError(f'Got an unknown source {source}')


def get_starting_bond_topology_index(conformer):
  """Gets the index of the bond topology which generated this calculation.

  If there is only a single geometry, it's that one.
  Otherwise, one of the geometries should be marked with is_starting_topology

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    integer

  Raises:
    ValueError: if no starting topology can be found
  """
  if len(conformer.bond_topologies) == 1:
    return 0
  for i in range(len(conformer.bond_topologies)):
    if conformer.bond_topologies[i].is_starting_topology:
      return i

  raise ValueError(
      f'For conformer {conformer.conformer_id}, no starting topology')


def conformer_to_bond_topology_summaries(conformer):
  """Produces BondTopologySummary protos from Conformer.

  Since a conformer can be associated with many bond topologies, this can output
  potentially many summaries.

  Args:
    conformer: dataset_pb2.Conformer

  Yields:
    dataset_pb2.BondTopologySummary
  """
  summary = dataset_pb2.BondTopologySummary()
  try:
    starting_idx = get_starting_bond_topology_index(conformer)
    summary.bond_topology.CopyFrom(conformer.bond_topologies[starting_idx])
    summary.count_attempted_conformers = 1
  except ValueError:
    starting_idx = None
    # In this case, we won't yield the summary at all so we don't set anything
    # about it.

  def other_topologies():
    if starting_idx is None:
      yield from conformer.bond_topologies
    else:
      yield from itertools.chain(conformer.bond_topologies[:starting_idx],
                                 conformer.bond_topologies[(starting_idx + 1):])

  fate = conformer.fate

  if fate == dataset_pb2.Conformer.FATE_UNDEFINED:
    raise ValueError(f'Conformer {conformer.conformer_id} has undefined fate')
  elif fate == dataset_pb2.Conformer.FATE_DUPLICATE_SAME_TOPOLOGY:
    summary.count_duplicates_same_topology = 1
  elif fate == dataset_pb2.Conformer.FATE_DUPLICATE_DIFFERENT_TOPOLOGY:
    summary.count_duplicates_different_topology = 1
  elif (fate == dataset_pb2.Conformer.FATE_GEOMETRY_OPTIMIZATION_PROBLEM or
        fate == dataset_pb2.Conformer.FATE_DISASSOCIATED or
        fate == dataset_pb2.Conformer.FATE_FORCE_CONSTANT_FAILURE or
        fate == dataset_pb2.Conformer.FATE_DISCARDED_OTHER):
    summary.count_failed_geometry_optimization = 1
  elif fate == dataset_pb2.Conformer.FATE_NO_CALCULATION_RESULTS:
    summary.count_kept_geometry = 1
    summary.count_missing_calculation = 1
  elif (fate == dataset_pb2.Conformer.FATE_CALCULATION_WITH_SERIOUS_ERROR or
        fate == dataset_pb2.Conformer.FATE_CALCULATION_WITH_MAJOR_ERROR or
        fate == dataset_pb2.Conformer.FATE_CALCULATION_WITH_MODERATE_ERROR):
    summary.count_kept_geometry = 1
    summary.count_calculation_with_error = 1
    for bt in other_topologies():
      other_summary = dataset_pb2.BondTopologySummary()
      other_summary.bond_topology.CopyFrom(bt)
      other_summary.count_detected_match_with_error = 1
      yield other_summary
  elif (
      fate == dataset_pb2.Conformer.FATE_CALCULATION_WITH_WARNING_SERIOUS or
      fate == dataset_pb2.Conformer.FATE_CALCULATION_WITH_WARNING_VIBRATIONAL):
    summary.count_kept_geometry = 1
    summary.count_calculation_with_warning = 1
    for bt in other_topologies():
      other_summary = dataset_pb2.BondTopologySummary()
      other_summary.bond_topology.CopyFrom(bt)
      other_summary.count_detected_match_with_warning = 1
      yield other_summary
  elif fate == dataset_pb2.Conformer.FATE_SUCCESS:
    summary.count_kept_geometry = 1
    summary.count_calculation_success = 1
    for bt in other_topologies():
      other_summary = dataset_pb2.BondTopologySummary()
      other_summary.bond_topology.CopyFrom(bt)
      other_summary.count_detected_match_success = 1
      yield other_summary
  else:
    raise ValueError(f'Did not understand {fate}')

  if starting_idx is not None:
    yield summary


def conformer_eligible_for_topology_detection(conformer):
  """Returns whether this conformer is worthy of topology detection.

  Simple duplicate marking or conformers with unreliable geometries are not
  generally useful to do topology detection.

  Args:
    conformer: dataset_pb2.Conformer

  Returns:
    bool
  """
  return (conformer.duplicated_by == 0 and
          conformer.properties.errors.status >= 0 and
          conformer.properties.errors.status < 512)
