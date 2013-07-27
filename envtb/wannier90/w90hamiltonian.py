"""
Alle Funktionen durchtesten!!!! Sparse matrix Umstellung hat vl noch
Spuren hinterlassen
# XXX: Bugfix bei mixin Hamiltonian
"""

from envtb import general
import numpy
import math
import cmath
from envtb.vasp import poscar
from scipy import linalg
from matplotlib import pyplot
from matplotlib.path import Path
import matplotlib.patches as patches
import itertools
from scipy import sparse

import glob
import os.path
import numpy.linalg
import re
import envtb.quantumcapacitance.utilities as utilities
#from mayavi import mlab
import envtb.utility.fourier

class Hamiltonian:
    
    
    """
    TODO: durchschleifen der argumente bei bloch_eigenvalues etc. ist bloed. vl. argumente bei allen anderen
    mit *args und auf dokumentation von bloch_eigenvalues verweisen?
    TODO: unitcellcoordinates and numbers is used ambiguously
    TODO: performance: use in-place operations for numpy -=, +=, *= and consider numpy.fromfunction
    TODO: to ensure a variable is a numpy array: a = array(a, copy=False)
    TODO: REFACTOR REFACTOR REFACTOR
    TODO: sparse matrices: http://docs.scipy.org/doc/scipy/reference/sparse.html, 
          http://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.eigs.html#scipy.sparse.linalg.eigs
    TODO: plots konsistenter zur aussenwelt machen, dh steuerung von aussen erlauben (mehrere
          plots uebereinander, nebeneinander etc.
    TODO: alles sparse + abgeleitete hamiltonians auf die alten verweisen,
          nicht explizit schreiben
    TODO: moeglichkeit zu einem output-logfile mit versionsnummer, zB
          mit globaler variable LOG

    TODO; die reihenfolge in create_supercell ist komisch, zB beruecksichtigt energy_shift schon die vergroesserung
          der zelle
    TODO: apply_electrostatic_potential fuer alle fkten mit 1,2,3 argumenten
    TODO: remove pyplot dependencies: always take axes and return lines (or
          something similar pragmatic)
    """
    
    __unitcellmatrixblocks=[]
    __unitcellnumbers=[]
    __orbitalspreads=[]
    __orbitalpositions=[]
    #TODO: make a map/dictionary out of those two
    __latticevecs=0
    __nrbands=0
    __fermi_energy=None
    
    def __init__(self):
        """
        There are several ways to initialize the Wannier90 Hamiltonian:
        1) Hamiltonian.from_file(wannier90filename,poscarfilename,wannier90woutfilename)
        2) Hamiltonian.from_raw_data(unitcellmatrixblocks,unitcellnumbers,latticevecs,orbitalspreads,orbitalpositions)
        3) Hamiltonian.from_nth_nn_list(nnfile,customhopping):
        
        See the documentation of those methods.
        """

        try:
            from mpi4py import MPI
            self.mpi_comm = MPI.COMM_WORLD
            self.mpi_size = self.mpi_comm.Get_size()
            self.mpi_rank = self.mpi_comm.Get_rank()
        except ImportError:
            self.mpi_comm = None
            self.mpi_size = 0
            self.mpi_rank = 0
                
        #TODO: wannier90filename should be the id of the wannier90 calculation, and specific
        #filenames derived from that ('bla' -> bla.win, bla.wout, bla_hr.dat etc.). Then,
        #kick out all filename method arguments
        
    def fermi_energy(self):
        """
        Return the system's Fermi energy.
        """
        return self.__fermi_energy
        
    def latticevectors(self):
        """
        Return the system's lattice vectors.
        """
        
        return numpy.array(self.__latticevecs.latticevecs()) #copy
    
    def reciprocal_latticevectors(self):
        """
        Return the system's reciprocal lattice vectors.
        """
        
        return numpy.array(self.__latticevecs.reciprocal_latticevecs()) #copy
    
    def orbitalspreads(self):
        """
        Return the wannier90 orbital spreads.
        """
        
        return list(self.__orbitalspreads)
    
    def orbitalpositions(self):
        """
        Return the wannier90 orbital positions.
        """
        
        return list(self.__orbitalpositions) 
        
    @classmethod
    def from_file(cls,wannier90filename,poscarfilename,wannier90woutfilename,outcarfilename):
        """
        A constructor to create an object based on data from files.
        wannier90filename: Path to the wannier90_hr.dat file
        poscarfilename: Path to the VASP POSCAR file
        wannier90woutfilename: Path to the wannier90.wout file
        outcarfilename: Path to the VASP OUTCAR file
        """        
        self = cls()
        
        poscardata = poscar.PoscarData(poscarfilename)
        self.__latticevecs=poscardata.lattice_vectors
        self.__nrbands,wanndata = self.__read_wannier90_hr_file(wannier90filename)
        self.__unitcellmatrixblocks, self.__unitcellnumbers = self.__process_wannier90_hr_data(wanndata)
        self.__orbitalspreads,self.__orbitalpositions=self.__orbital_spreads_and_positions(wannier90woutfilename)
        self.__fermi_energy=self.__get_fermi_energy_from_outcar(outcarfilename)
        
        return self
    
    @classmethod
    def from_raw_data(cls,unitcellmatrixblocks,unitcellnumbers,latticevecs,orbitalspreads,orbitalpositions,fermi_energy):
        """
        A constructor used to create a custom Hamiltonian.
        unitcellmatrixblocks: Hopping elements, arranged by unit cells.
        unitcellnumbers: coordinates of the unit cells "hopped" to.
        latticevecs: lattice vectors.
        orbitalspreads: spreads of the orbitals
        orbitalpositions: positions of the orbitals
        """              
        self = cls()
        
        self.__unitcellnumbers = unitcellnumbers
        self.__unitcellmatrixblocks = unitcellmatrixblocks
        self.__latticevecs = poscar.LatticeVectors(latticevecs)
        self.__nrbands = unitcellmatrixblocks[0].shape[0]
        self.__orbitalspreads=orbitalspreads
        self.__orbitalpositions=orbitalpositions
        self.__fermi_energy=fermi_energy
        
        return self
        
    @classmethod        
    def from_nth_nn_list(cls,nnfile,customhopping=None):
        """
        A constructor to create a nth-nearest-neighbour Hamiltonian.
        
        nnfile: File containing the system information (see example data)
        customhopping: Dictionary, containing hopping parameters overriding those in nnfile.
                       Example: {0:ONSITE,1:1STNN,2:2NDNN}
        """
        self = cls()
        
        latticevecs,nndata,orbitalspreads,orbitalpositions,defaulthopping=self.__read_nth_nn_file(nnfile)    
        
        if customhopping==None:
            hopping=numpy.zeros(max(defaulthopping.keys())+1)
        else:
            hopping=numpy.zeros(max(max(defaulthopping.keys()),max(customhopping.keys()))+1)
        
        for i,v in defaulthopping.items():
            hopping[i]=v
        
        if customhopping!=None:
            for key,val in customhopping.items():
                hopping[key]=val
            
        nrbands=len(orbitalspreads)
        
        unitcellmatrixblocks,unitcellnumbers=self.__process_nth_nn_data(nndata,hopping,nrbands)
        
        self.__unitcellnumbers = unitcellnumbers
        self.__unitcellmatrixblocks = unitcellmatrixblocks
        self.__latticevecs = poscar.LatticeVectors(latticevecs)
        self.__nrbands = nrbands
        self.__orbitalspreads=orbitalspreads
        self.__orbitalpositions=orbitalpositions
        
        return self
    
    def __get_fermi_energy_from_outcar(self,outcarfilename):
        f = open(outcarfilename, 'r')
        lines = f.readlines()
        
        for nr,line in enumerate(lines):
            ret = line.find("E-fermi :")
            if ret >=0:
                fermi_energy=float(lines[nr].split()[2])
                return fermi_energy
                
        raise ValueError('Fermi energy not found in OUTCAR file')
        
    def __read_nth_nn_file(self,nnfile):
        latticevecsstr,orbdatastr,defaulthoppingstr,nndatastr=general.split_by_empty_lines(general.read_file_as_table(nnfile),True)
        
        latticevecs=[[float(x) for x in line] for line in latticevecsstr]
        nndata=[[int(x) for x in line] for line in nndatastr]
        orbitalspreads=[float(line[0]) for line in orbdatastr]
        orbitalpositions=[[float(x) for x in line[1:]] for line in orbdatastr]
        
        defaulthoppingindices=[int(x[0]) for x in defaulthoppingstr]
        defaulthoppingvals=[float(x[1]) for x in defaulthoppingstr]
        defaulthopping=dict(zip(defaulthoppingindices,defaulthoppingvals))
        
        return latticevecs,nndata,orbitalspreads,orbitalpositions,defaulthopping
        
    def __process_nth_nn_data(self,nndata,hopping,nrbands):
        prevcell = []
        unitcells = []
        for line in nndata:
            currentcell = line[0:3]
            if currentcell != prevcell:
                unitcells.append([])
            unitcells[-1].append(line)
            prevcell = currentcell
        unitcellnumbers = [[x for x in unitcell[0][0:3]] for unitcell in unitcells]

        unitcellmatrixblocks = []
        
        for unitcell in unitcells:
            block=sparse.lil_matrix((nrbands,nrbands))
            for element in unitcell:
                block[element[3],element[4]]=hopping[element[5]]
            unitcellmatrixblocks.append(block.tocsr())
                
        return unitcellmatrixblocks,unitcellnumbers
        
    def __process_wannier90_hr_data(self, wanndata):
        """
        Reads hopping matrix elements from wanndata into object. wanndata is a list
        of lines, each line being a list in the following format:
        veca vecb vecc thisorb otherorb re im
        
        veca,vecb,vecc: Unit cell coordinates of other cell
        thisorb: Nr of orbital in main cell
        otherorb: Nr of orbital in other cell
        re, im: Hopping matrix element
        
        Hopping matrix elements have to be sorted by unit cell coordinates (veca,vecb,vecc).
        Then, they have to be sorted by thisorb and otherorb, with thisorb running faster
        than otherorb.
        """
        prevcell = []
        unitcells = []
        for line in wanndata:
            currentcell = line[0:3]
            if currentcell != prevcell:
                unitcells.append([])
            unitcells[-1].append(line)
            prevcell = currentcell
        
        unitcellnumbers = [[int(x) for x in unitcell[0][0:3]] for unitcell in unitcells]
        unitcellmatrixblocks = []
        for unitcell in unitcells:
            elementlist = numpy.array([complex(float(line[5]), float(line[6])) for line in unitcell]) 
            unitcellmatrixblocks.append(sparse.lil_matrix(numpy.transpose(elementlist.reshape((self.__nrbands, self.__nrbands))))) #Transpose because first index in wannier90_hr.dat file runs faster than second
            #automatically disregards small entries - threshold unknown to me :)
        
        return unitcellmatrixblocks, unitcellnumbers

    def __read_wannier90_hr_file(self,filename):
        data=general.read_file_as_table(filename)
        
        nrbands=int(data[1][0])
        linestart=int(math.ceil(float(data[2][0])/15))+3
        wanndata=data[linestart:]
        
        return nrbands,wanndata
        #scipy.linalg.blas.fblas.zaxpy
        
    def __bloch_phases(self,k):
        """
        Calculates the bloch factor e^ikr for each unit cell in
        self.__unitcellnumbers
        """
        #TODO: if k is direct: lattice vectors are probably not necessary. How could that work?
        latticevecs_transposed=numpy.transpose(self.__latticevecs.latticevecs())
        return numpy.array([cmath.exp(complex(0,1)*numpy.dot(k, \
        numpy.dot(latticevecs_transposed,cellnumber))) for cellnumber in self.__unitcellnumbers])
        
    def __unitcellcoordinates_to_nrs(self,usedhoppingcells):
        """
        Given a list of unit cell coordinates, the function
        converts them to integer indices i for __unitcellmatrixblocks[i] and
        __unitcellnumbers[i].
        """
        
        indices=[]
        for cell in usedhoppingcells:
            index=self.__unitcellnumbers.index(cell)
            indices.append(index)
            
        return indices
    
    def __sorting_order(self,data,key=None):
        """
        Sorts a list by the given column sortcolumn and returns the order. 
        If key==None (default), all columns are sorted, with the last column running fastest.
        E.g. for sorting by the second column, set key=lambda w: w[1]
        """
        if key==None:
            return [i[0] for i in sorted(enumerate(data),key=lambda x: x[1])]
        else:
            return [i[0] for i in sorted(enumerate(data),key=lambda x: key(x[1]))]
    
    
    def __apply_order(self,data,order):
        """Applies an order to a list."""
        return [data[i] for i in order]
    
    def write_matrix_elements(self,outputfile,usedhoppingcells='all',usedorbitals='all'):
        """
        Write the wannier90 matrix elements to a file (*.wetb) readable by Florian's code.
        Information contained in the file:
        - lattice vectors
        - orbital positions
        - orbital spreads
        - matrix elements of the chosen unit cells and orbitals
        
        Description of the file format:
        The file contains three sections, divided by an arbitrary number of blank lines (one at least,
        obviously). Lines starting with # are comments and are ignored. Anything in a line after the
        data is also ignored (i.e. you can write anything in the same line after the data, with or
        without #).
        First block: lattice vectors in rows
        Second block: orbital spread (first column) and position (other columns) of every orbital
        Third block: Matrix elements.
            Column 1-3: Unit cell number
            Column 4: Orbital number in main unit cell
            Column 5: Orbital number in other unit cell (the one the electron "hops" to)
            Column 6&7: Real & imaginary part of the matrix element
        
        outputfile: Name of the output file (*.wetb - Wannier90-Environmental-dependent-Tight-Binding)
        usedhoppingcells: If you don't want to use all hopping parameters,
        you can set them here (get the list of available cells with unitcellnumbers() and
        strip the list from unwanted cells).
        usedorbitals: a list of used orbitals to use. Default is 'all'. Note: this only makes
        sense if the selected orbitals don't interact with other orbitals.
        """
        
        output=open(outputfile,'w')
        
        if usedhoppingcells == 'all':
            usedunitcellnrs=range(len(self.__unitcellnumbers))
        else:
            usedunitcellnrs=self.__unitcellcoordinates_to_nrs(usedhoppingcells)
            
        if usedorbitals=='all':
            orbitalnrs=range(self.__nrbands)
        else:
            orbitalnrs=usedorbitals
            
        order_usedunitcellnumbers=self.__apply_order(usedunitcellnrs, self.__sorting_order([self.__unitcellnumbers[i] for i in usedunitcellnrs]))
            
        output.write('#WETB File\n\n')
        output.write('#Lattice vectors:\n')
        latticevecs=self.__latticevecs.latticevecs()
        for vec in latticevecs:
            output.write('{:12.6f} {:12.6f} {:12.6f}\n'.format(*vec))
        output.write('\n\n')
        output.write('#Spreads and positions of the orbitals:\n')
        spreads=self.__orbitalspreads
        positions=self.__orbitalpositions
        for spread,position in zip(spreads,positions):
            output.write('{:12.6f} '.format(spread))
            output.write('{:12.6f} {:12.6f} {:12.6f}\n'.format(*position))
        output.write('\n\n')
        
        output.write('#Unit cell number, main orbital, other orbital, hopping element:\n')
        for i in order_usedunitcellnumbers:
            for j, val in numpy.ndenumerate(self.__unitcellmatrixblocks[i][numpy.ix_(orbitalnrs,orbitalnrs)]):
                #j: ndenumerate assigns the hop-from and hop-to number to each hopping matrix element
                
                #http://docs.python.org/library/string.html#format-specification-mini-language
                cellnrs=self.__unitcellnumbers[i]
                output.write('{:5d} {:5d} {:5d} '.format(*cellnrs))
                output.write('{:5d} {:5d} '.format(*j))
                output.write('{:12.6f} {:12.6f}\n'.format(val.real,val.imag))
                            
                
        
        output.close()    
    
    def maincell_eigenvalues(self,solver='dense',return_evecs=False,**kwargs):
        """
        Calculates the eigenvalues of the main cell (no hopping to adjacent unit cells).
        
        solver: eigenvalue solver. There are:
            'dense': Assuming a dense matrix; returns all eigenvalues. Uses
            scipy.linalg.eig. E.g.
            >>> evals=ham.maincell_eigenvalues()
            'scipy_arpack': find a given number of eigenvalues and eigenvectors of
            a BIG, SPARSE matrix (including shift-invert). It can never give you
            all eigenvalues. Uses ARPACK through scipy.sparse.linalg.eigsh.
            You have to supply additional parameters for eigsh using **kwargs, e.g.
            >>> ham.maincell_eigenvalues('arpack',k=10,sigma=0.0,ncv=100)
            See http://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.eigsh.html
            for the available parameters. You will probably need k,sigma, and maybe nvc, which.
            Consider using which='SM' if E_F=0.
        return_evecs: Also return eigenvectors.
        """
        
        #XXX: Make solver an abstract class
        blochmatrix = self.__unitcellmatrixblocks[self.__unitcellcoordinates_to_nrs([[0,0,0]])[0]]
        
        evals=None
        evecs=None
        
        if return_evecs and solver=='scipy_arpack':
            raise NotImplementedError
        
        if solver=='scipy_arpack':
            #http://docs.scipy.org/doc/scipy/reference/tutorial/arpack.html
            #XXX: inverter superlu works best with csc matrices. Can one do something about that?
            #XXX: k=10 --> vectors have length 10? WRONG!!!
            evals,evecs=sparse.linalg.eigsh(blochmatrix,**kwargs)
            #return numpy.sort(evals.real)
        elif solver=='dense':
            evals,evecs=linalg.eig(blochmatrix.todense())
            #return numpy.sort(evals.real)
        else:
            raise ValueError('Supplied solver not found')
        
        if return_evecs:
            evals_ordering=self.__sorting_order(evals)
            return numpy.array(self.__apply_order(evals,evals_ordering)), numpy.array(self.__apply_order(evecs,evals_ordering))
        else:
            return numpy.sort(evals.real)
        
    def maincell_hamiltonian_matrix(self):  
        """
        Returns the Hamiltonian matrix for the main cell, without hopping
        parameters to other cells. This is the matrix whose eigenvalues
        you can calculate using maincell_eigenvalues().      
        """ 
                   
        return self.__unitcellmatrixblocks[self.__unitcellcoordinates_to_nrs([[0,0,0]])[0]]
    
    def bloch_eigenvalues(self,k,basis='c',usedhoppingcells='all',return_evecs=False, dense_blocks=None):
        """
        Calculates the eigenvalues of the eigenvalue problem with
        Bloch boundary conditions for a given vector k.
        
        The function uses a dense matrix eigenvalue solver because it returns all
        eigenvalues, so don't let the matrices get too big.
        
        usedhoppingcells: If you don't want to use all hopping parameters,
        you can set them here (get the list of available cells with unitcellnumbers() and
        strip the list from unwanted cells).
        basis: 'c' or 'd'. Determines if the kpoints are given in cartesian
        reciprocal coordinates or direct reciprocal coordinates.
        return_evecs: If True, evecs are also returned as the second return value.
        dense_blocks: if the function is invoked many times, supply the dense matrix blocks to increase
        speed. Create them with dense_blocks=[block.toarray() for block in self.__unitcellmatrixblocks].
        
        """
        
        if usedhoppingcells == 'all':
            usedunitcellnrs=range(len(self.__unitcellnumbers))
        else:
            usedunitcellnrs=self.__unitcellcoordinates_to_nrs(usedhoppingcells)
        
        if basis=='d':
            k=self.__latticevecs.direct_to_cartesian_reciprocal(k)
            
        orbitalnrs=range(self.__nrbands)
        
        bloch_phases=self.__bloch_phases(k)
        #I think this needs lil_matrix, coo_matrix didn't work.
        #blochmatrix = sparse.lil_matrix((len(orbitalnrs), len(orbitalnrs)), dtype=complex)
        blochmatrix = numpy.zeros((len(orbitalnrs), len(orbitalnrs)), dtype=complex)
        
        if dense_blocks is None:
            for i in usedunitcellnrs:
                blochmatrix += bloch_phases[i] * self.__unitcellmatrixblocks[i]
        else:
            for i in usedunitcellnrs:
                blochmatrix += bloch_phases[i] * dense_blocks[i]        

        evals,evecs=linalg.eig(blochmatrix)
        
        if return_evecs==True:
            evals_ordering=self.__sorting_order(evals)
            return numpy.array(self.__apply_order(evals,evals_ordering)), numpy.array(self.__apply_order(evecs,evals_ordering))
        else:
            return numpy.sort(evals.real)
            
    def create_orbital_vector_list(self,vector,include_third_dimension=False,include_spread=False):
        """
        Create a list of orbital positions with given eigenvector amplitudes. Only the real part from
        the eigenvector is kept.
        
        vector: Vector to connect to the orbital positions.
        include_third_dimension: Include the z position of the points. Default is False.
        include_spread: Include the spread of the orbital. Default is False.
        
        Return: A matrix containing the following columns:
                x   y   (z)   (spread)    value
        """
        
        if include_third_dimension==True:
            pos=numpy.array(self.__orbitalpositions)
        else:
            pos=numpy.array(self.__orbitalpositions)[:,0:2]
            
        if include_spread==True:
            pos=numpy.append(pos,numpy.real(numpy.transpose([self.__orbitalspreads])),1)
        
        pos=numpy.append(pos,numpy.real(numpy.transpose([vector])),1)
        
        return pos
        
    def plot_vector(self,vector,scale=1,figsize=None):
        """
        Plot a vector with geometry by putting circles on the positions of the orbitals.
        The size of the circles corresponds to the absolute square, the color to the sign.
        
        vector: vector to plot
        scale: scale factor for the circles.
        figsize: w,h tuple in inches
        """
        
        pyplot.figure(figsize=figsize)
        pyplot.axes().set_aspect('equal','datalim')
        colors=['r' if x>0 else 'b' for x in vector]
        pos=numpy.array(self.__orbitalpositions)
        pyplot.scatter(pos[:,0],pos[:,1],scale*numpy.abs(vector)**2,c=colors,edgecolors='none')
        
    def plot_orbital_positions(self):
        """
        Plot the positions of the orbitals in the unit cell.
        """
        
        self.plot_vector(10*numpy.ones(len(self.__orbitalpositions)))
    
    def bandstructure_data(self,kpoints,basis='c',usedhoppingcells='all'):
        """
        Calculates the bandstructure for a given kpoint list.
        For direct plotting, use plot_bandstructure(kpoints,filename).
                
        If kpoints is a string, this string will be interpreted as the
        name of the crystal structure (see standard_paths), and the crystal
        structure's default kpoint path will be used.
        
        usedhoppingcells: If you don't want to use all hopping parameters,
        you can set them here (get the list of available cells with unitcellnumbers() and
        strip the list from unwanted cells).        
        basis: 'c' or 'd'. Determines if the kpoints are given in cartesian
        reciprocal coordinates or direct reciprocal coordinates.

        Return:
        A list of eigenvalues for each kpoint is returned. To sort 
        by band, use data.transpose().

        If MPI is used, ONLY THE ROOT PROCESS returns the data, the others
        return None.
        """
        
        if isinstance(kpoints,str):
            kpoints=self.standard_paths(kpoints)[2]
            basis='d'


        if self.mpi_comm:
            if self.mpi_rank == 0:
                path_parts = numpy.array_split(kpoints,self.mpi_size)
            else:
                path_parts = None

            path=self.mpi_comm.scatter(path_parts,root=0)
        else:
            path=kpoints

        dense_blocks=[block.toarray() for block in self.__unitcellmatrixblocks]
        data=numpy.array([self.bloch_eigenvalues(kpoint,basis,usedhoppingcells,dense_blocks=dense_blocks)
                          for kpoint in path])

        if self.mpi_comm:
            allbsdata=None
            allbsdata=self.mpi_comm.gather(data,root=0)
        
            if self.mpi_rank==0:
                return numpy.concatenate(allbsdata)
#        allbsdata=numpy.empty((len(kpoints),self.__nrbands))
#        comm.Allgather([data,MPI.DOUBLE],[allbsdata,MPI.DOUBLE])
            else:
                return None
        else:
            return data
    
    def point_path(self,corner_points,nrpointspersegment):
        """
        Generates a path connecting the corner_points with nrpointspersegment points per segment
        (excluding the next point), resulting in sum(nrpointspersegment)+1 points.
        The points in corner_points can have any dimension.
        nrpointspersegment is a list with one element less than corner_points.
        If nrpointspersegment is an integer, it is assumed to apply to each segment.
        
        Example: 
        my_hamiltonian.point_path([[0,0],[1,1],[2,2]],[2,2])
        gives        
        [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0], [1.5, 1.5], [2, 2]]
        (note: those are 5 points, which is sum([2,2])+1)
        
        or equivalently:
        my_hamiltonian.point_path([[0,0],[1,1],[2,2]],2)
        """
        """TODO: maybe put this function somewhere else?"""

        if type(nrpointspersegment) != int and len(corner_points) != len(nrpointspersegment)+1:
            raise ValueError('corner_points has to be one element larger than nrpointspersegment, unless nrpointspersegment is integer.')
        if type(nrpointspersegment)==int:
            nrpointspersegment=(len(corner_points)-1)*[nrpointspersegment]
        if type(corner_points[0])!=list:
            corner_points=[[x] for x in corner_points]

        points=[]
        for i in range(len(nrpointspersegment)):
            newpoints=self.__path_between_two_vectors(corner_points[i], corner_points[i+1], nrpointspersegment[i])
            points.extend(newpoints)
            
        points.append(corner_points[-1])
            
        return points
    
    def __path_between_two_vectors(self,v1,v2,nrpoints):
        """
        Generates a path between v1 and v2 (lists of any dimension) with nrpoints elements.
        The last point, v2, is not in the path.
        """
        dimension=len(v1)
        return numpy.transpose([numpy.linspace(v1[j], \
                v2[j],nrpoints,endpoint=False) for j in range(dimension)]).tolist()
        
    def plot_bandstructure(self,kpoints,filename=None,basis='c',usedhoppingcells='all',mark_reclattice_points=False,mark_fermi_energy=False,axes=None):
        """
        Calculate the bandstructure at the points kpoints (given in 
        cartesian reciprocal coordinates - use direct_to_cartesian_reciprocal(k)
        if you want to use direct coordinates) and save the plot
        to filename. The ending of filename determines the file format. If 
        filename=None (default), the plot will not be saved (you can display
        it using pyplot.show() ).
        
        If kpoints is a string, this string will be interpreted as the
        name of the crystal structure (see standard_paths), and the crystal
        structure's default kpoint path will be used.
        
        usedhoppingcells: If you don't want to use all hopping parameters,
        you can set them here (get the list of available cells with unitcellnumbers() and
        strip the list from unwanted cells).  
        basis: 'c' or 'd'. Determines if the kpoints are given in cartesian
        reciprocal coordinates or direct reciprocal coordinates.
        mark_reclattice_points: You can mark important reciprocal lattice points, like
        \Gamma or K. This variable can be (i) True if you use a string for kpoints
        (ii) a list which contains the names of the points and the points:
        mark_reclattice_points=[names,points]. The points have to be in 
        cartesian coordinates. Default is False.
        mark_fermi_energy: If you supply the Fermi energy here, a line will be
        drawn. If True, the Fermi energy will be taken from fermi_energy().
        Default is False.
        axes: axes to draw into. If None, a new plot will be created.
        
        If MPI is used, ONLY THE ROOT PROCESS plots. This coincides with bandstructure_data,
        where also only the root process returns all the bandstructure data.
        
        Return:
        lines: List of matplotlib.lines.Line2D objects that were drawn. You
        can change the style, color etc., like:
            for line in lines:
                line.set_color('red')
        fermi_energy_line: The fermi energy mark Line2D object.
        lattice_point_lines: The lattice point marks Line2D object.
        """

        data=self.bandstructure_data(kpoints,basis,usedhoppingcells)

        if axes is None:
            fig=pyplot.figure()
            axes=fig.add_subplot(111)

        if self.mpi_rank == 0:

            bplot=BandstructurePlot(axes)
        
            if isinstance(kpoints,str):
                reclattice_points,reclattice_names,kpoints=self.standard_paths(kpoints)
                basis='d'
            
            lattice_point_lines=None
            fermi_energy_line=None
            
            lines=bplot.plot(kpoints, data)
            if not isinstance(mark_fermi_energy,bool):
                fermi_energy_line=bplot.plot_fermi_energy(mark_fermi_energy)
            elif mark_fermi_energy:
                fermi_energy_line=bplot.plot_fermi_energy(self.fermi_energy())
            
            if mark_reclattice_points != False:
                if mark_reclattice_points == True:
                    lattice_point_lines=bplot.plot_lattice_point_vlines(reclattice_points, reclattice_names)
                else:
                    pass
            if filename!=None:
                pyplot.savefig(filename)
            
            return lines,fermi_energy_line,lattice_point_lines

        return
        
    def drawunitcells(self,ax,unitcellnumbers='all'):
        """
        Create a plot of a list of unit cells.
        
        unitcellnumbers: Numbers of unit cells to plot.
        Default value is 'all', then unitcellnumbers() is used.
        """
        
        if unitcellnumbers == 'all':
            unitcellnumbers=self.__unitcellnumbers
        
        cellstructure=numpy.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,0]])
        lv=self.__latticevecs.latticevecs()
        unitcellform=numpy.dot(cellstructure,lv)[:,:2]
        cellcoords=self.unitcellcoordinates(unitcellnumbers)[:,:2]
        maincell=unitcellnumbers.index([0,0,0])
        verticeslist=numpy.array([[formpoint+cellcoordinate for formpoint in unitcellform] for cellcoordinate in cellcoords])
        maincellvertices=verticeslist[maincell]
        verticeslist=numpy.delete(verticeslist,maincell,axis=0)   
        
        #http://matplotlib.sourceforge.net/users/path_tutorial.html
        
        codes = [Path.MOVETO,
         Path.LINETO,
         Path.LINETO,
         Path.LINETO,
         Path.CLOSEPOLY,
         ]
        
        for verts in verticeslist:
            path = Path(verts, codes)
            patch = patches.PathPatch(path, facecolor='white', lw=2)
            ax.add_patch(patch)
        

        path = Path(maincellvertices, codes)
        patch = patches.PathPatch(path, facecolor='orange', lw=2)
        ax.add_patch(patch)
        
        ax.set_xlim(-40,40)
        ax.set_ylim(-40,40)      
           
        
    def unitcellcoordinates(self,unitcellnumbers='all'):
        """
        Cartesian coordinates of the given unit cells.
        
        unitcellnumbers: a list of the unit cell numbers. 
        Default value is 'all', then unitcellnumbers() is used.
        """
        
        """
        How the formula works:
        
        The unitcellnumbers are the coordinates of the unit
        cells in the basis spanned by the lattice vectors. A transformation
        to cartesian coordinates is just a basis transformation. The columns of
        the transformation matrix are the lattice vectors in cartesian
        coordinates --> we just have to transpose the list of lattice vectors.
        Instead of applying the transformation matrix to each vector, we apply
        it to all of them at the same time by writing the vectors in the columns
        of a matrix (=transposing the list of unit cell numbers).
        Since the transformed vectors are in the columns of the result matrix,
        we need to transpose that one again.
        
        The formula is now (' = transpose):
        (latticevecs' unitcellnumbers')'
        
        But this is:
        (A'B')'=((BA)')'=BA
        
        -->
        unitcellnumbers latticevecs
        
        So that's the formula!
        
         
        """
        latticevecs = self.__latticevecs.latticevecs()
        
        if unitcellnumbers == 'all':
            unitcellnumbers=numpy.array(self.__unitcellnumbers)
        
        return numpy.dot(unitcellnumbers,latticevecs)
    
    def unitcells_within_zone(self,zone,basis='c',norm_order=2):
        """
        Returns a list of unit cells within a certain area. The function
        is comparing the same point in each cell (e.g. always the bottom left end).
        
        zone: can be a number or a tuple:
            number: radius to include cells within.
            tuple: area to include cells within, in the sense of distance from the origin along a direction.
            
        basis: determines if zone is given in cartesian ('c') or direct ('d') coordinates.
        IMPORTANT: If direct coordinates are used, use integers for zone, not float!
        
        norm_order: if zone is a number (=radius), norm_order is the norm to use (mathematical definition, see 
        http://docs.scipy.org/doc/numpy/reference/generated/numpy.linalg.norm.html). Default is 2 (=Euclidean norm)
        Short version: 2 gives you a "circle", numpy.inf a "square".
        
        Examples:
        Cells within 30 Angstrom:
        unitcells_within_zone(30)
        Cells within a 6x8x1 Angstrom cuboid:
        unitcells_within_zone((3.0,4.0,0.5))
        Cells within a 4x4x4 block in direct coordinates:
        unitcells_within_zone((2,2,2),'d')
        """
        
                
        if type(zone) is tuple:
            if basis == 'd':
                zone=abs(numpy.array(zone))
            if basis == 'c':
                reclattice_transposed_inverted=linalg.inv(self.__latticevecs.reciprocal_latticevecs().transpose()) #matrix to transform from cartesian to direct coordinates
                zone=abs(numpy.dot(reclattice_transposed_inverted,numpy.array(zone)))
            unitcellnrs=[unitcellnr for unitcellnr in self.__unitcellnumbers if numpy.floor(numpy.amin(zone-abs(numpy.array(unitcellnr))))>=0]
        else:
            if basis == 'c':
                unitcellnrs=[unitcellnr for unitcellcoords,unitcellnr 
                             in zip(self.unitcellcoordinates(),self.__unitcellnumbers) 
                             if numpy.linalg.norm(unitcellcoords)<=zone]
            if basis == 'd':    
                unitcellnrs=[unitcellnr for unitcellnr in self.__unitcellnumbers if numpy.linalg.norm(unitcellnr,norm_order)<=zone]
    
        return unitcellnrs
    
    def drop_dimension_from_cell_list(self,dimension,unitcellnumbers='all'):
        """
        Takes a list of unit cell coordinates and drops the x,y or/and z dimension
        from the list - this way you can create a 2D material from a 3D material
        or a 1D material from a 2D material. The function deletes all unit cell numbers
        that have a nonzero entry in that dimension.
        
        dimension: the dimension to drop: 0, 1 or 2. Can also be a list, e.g. (0,1) drops
        the first and second dimension. 
        unitcellnumbers: List of unit cell numbers. Default value is 'all'.
        """
        
        if unitcellnumbers=='all':
            unitcellnumbers=self.unitcellnumbers()
            
        stack=list(unitcellnumbers)
        
        if type(dimension) is int:
            dimension=[dimension]
            
        for i in dimension:
            stack = [x for x in stack if x[i]==0]
        
        return stack
        
        


    def hermitian_hoppinglist(self,unitcellnumbers):
        """
        The function removes unit cells from a list of unit cells whose "parity
        partners" are missing to ensure a Hermitian Bloch matrix.
        
        Return: kept, removed
        
        kept: Kept unit cell numbers
        removed: removed unit cell numbers (just for control purposes)
                
        If hopping to a specific unit cell is not used, one has to make sure
        that the parity inversed unit cell (=the cell with the "negative"
        coordinates") is also dropped.
        That's because the matrix elements of the bloch matrix look like this:
        
        ... + \gamma_i e^ikR + \gamma_i e^-ikR + ...
        
        The sum of the two terms is cos(ikR) and real.
        
        --> The function drops the terms which miss their partner and thus won't
        become real.
        
        Note: It makes sense to remove not only the "parity partner", but all unit
        cells which are identical due to symmetry.
        """
        
        stack = list(unitcellnumbers)
        kept = []
        removed = []
        while len(stack)>0:
            element=stack.pop()
            if element == [-i for i in element]: #true for origin
                kept.append(element)
            else:
                try:
                    index_partner=stack.index([-i for i in element])
                    partner=stack.pop(index_partner)
                    kept.append(element)
                    kept.append(partner)
                except ValueError: #raised if -element does not exist
                    removed.append(element)
        return kept,removed
       
            
    def unitcellnumbers(self):
        """
        Returns the numbers of the unit cells supplied in the wannier90_hr.dat
        file.
        """
        return list(self.__unitcellnumbers) #makes a copy instead of a reference
    
    def nrorbitals(self):
        """
        Returns the number of orbitals/bands.
        """
        return self.__nrbands
    
    def standard_paths(self,name,nrpointspersegment=100):
        """
        Gives the standard path for a Bravais lattice in
        direct reciprocal coordinates.
        
        At the moment, there are 'hexagonal', 'fcc', '1D' and '1D-symmetric'.
        
        name: Name of the lattice
        nrpointspersegment: optional; if > 1, a list of intermediate points connecting
        the main points is also returned and can be used for a 
        bandstructure path (nrpointspersegment points per segment).
        Default value: 100
        
        Return:
        points,names(,path)
        
        points: points in the path
        names: names of the points
        (path: path with intermediate points. Only returned if nrpointspersegment is > 1)
        """
        if name=='hexagonal':
            path = [
                    ('$\Gamma$',[0,0,0]),
                    ('K',[1./3,-1./3,0]),
                    ('M',[0.5,0,0]),
                    ('$\Gamma$',[0,0,0])
                    ]
        elif name=='fcc':
            path = [
                    ('$\Gamma$',[0,0,0]),
                    ('X',[1./2,1./2,0]),
                    ('W',[3./4,1./2,1./4]),
                    ('L',[1./2,1./2,1./2]),
                    ('$\Gamma$',[0,0,0]),
                    ('K',[3./4,3./8,3./8])
                    ]
        elif name=='1D':
            path = [
                    ('$\Gamma$',[0,0,0]),
                    ('M',[0.5,0,0])         
                    ]            
        elif name=='1D-symmetric':
            path = [
                    ('M',[-0.5,0,0]),   
                    ('$\Gamma$',[0,0,0]),
                    ('M',[0.5,0,0])
                    ]                        
        else:
            raise Exception("Bravais lattice name not found!")
            
        points=[x[1] for x in path]
        names=[x[0] for x in path]
        
        if nrpointspersegment > 1:
            path=self.point_path(points, nrpointspersegment)
            return points,names,path
        else:
            return points,names
        
    def __orbital_spreads_and_positions(self,wannier90_wout_filename):
        """
        Reads the final wannier90 orbital spreads and positions from the
        wannier90.wout file.
        
        wannier90_wout_filename: path to the wannier90.wout file.
        
        Return:
        spreads,positions
        """
        
        #TODO: What about performance? Stuff gets copied pretty often
        #maybe use this http://stackoverflow.com/a/4944929/1447622
        
        f = open(wannier90_wout_filename, 'r')
        lines = f.readlines()
        
        splitspaces = [[x.strip(',') for x in line.split()] for line in lines]
        #Catastrophe - only a Flatten[] command, but unreadable
        infile = [list(itertools.chain(*[x.split(',') for x in line])) for line in splitspaces]
        
        for nr,line in enumerate(lines):
            ret = line.find("Number of Wannier Functions")
            if ret >=0:
                break
            
        nrbands=int(infile[nr][6])
        
        start = infile.index(["Final","State"])
        data = infile[start+1:start+nrbands+1]
        
        f.close()
        
        spreads = [float(x[10]) for x in data]
        positions = [[float(x[6][:-1]),float(x[7][:-1]),float(x[8])] for x in data]
        
        return spreads,positions
    
    def __remove_duplicates(self,seq):
        #http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates-from-a-list-in-python-whilst-preserving-order
        #http://www.peterbe.com/plog/uniqifiers-benchmark (f2)
        checked = []
        for e in seq:
            if e not in checked:
                checked.append(e)
        return checked        
    
    def create_supercell_hamiltonian(self,cellcoordinates,latticevecs,usedhoppingcells='all',usedorbitals='all',energyshift=None,magnetic_B=None,gauge_B='landau_x',mixin_ham=None,mixin_hoppings=None,mixin_cells=None,mixin_assoc=None,onsite_potential=None,output_maincell_only=False):
        """
        Creates the matrix elements for a supercell containing several unit cells, e.g. a volume
        with one unit cell missing in the middle or one slice of a nanoribbon.
        
        cellcoordinates: unit cells contained in the supercell [[0,0,0],[1,0,0],...]. Use integergrid3d()
        to easily create a unit cell grid (which you can modify).
        latticevectors: lattice vectors of the new unit cell in the basis of the old unit cells (!!).
        E.g. a supercell of four graphene unit cells could have latticevecs=[[2,0,0],[0,2,0],[0,0,1]]. 
        If you want to create a ribbon or a molecule, use a high value in one of the coordinates
        (e.g. a long y lattice vector).
        usedhoppingcells: If you don't want to use all hopping parameters, you can set the cells to "hop"
        to here (list of cell coordinates).
        usedorbitals: a list of orbitals to use. Default is 'all'. Note: this only makes
        sense if the selected orbitals don't interact with other orbitals. 
        energyshift: Shift energy scale by energyshift, e.g. to shift the Fermi energy to 0. Also shifts the Fermi
        energy variable of the Hamiltonian.
        magnetic_B: Magnetic field in perpendicular direction (in T)
        gauge_B: 'landau_x': Landau gauge for systems with x periodicity (A=(-By,0,0))
                 'landau_y:': Landau gauge for systems with y periodicity (A=(0,Bx,0))
                 'symmetric': Symmetric gauge for systems with x and y periodicity (A=1/2(-By,Bx,0))
        mixin_ham: A "mix-in" Hamiltonian from which some matrix elements are used. Default is None.
                   The mixin is done before the other modifications (magnetic field, energyshift)
        mixin_hoppings: A list of matrix elements from the main Hamiltonian that should be substituted with matrix elements from mixin_ham.
                        The conjugate hopping is generated automatically (i.e. (0,1) will be
                        automatically expanded to (0,1),(1,0) ). 
                        Example: Substitute all matrix elements from orbitals 0,1 to orbitals 0,1,2,3:
                        mixin_hoppings=[(0,0),(0,1),(0,2),(0,3),(1,0),(1,1),(1,2),(1,3)]
        mixin_cells: List of unit cells. Substitution can be restricted to specific unit cells.
                     E.g. the main cell: mixin_cells=[[0,0,0]]
                     E.g. the main cell and the ones left and right: mixin_cells=[[-1,0,0],[0,0,0],[1,0,0]]
                     Default is None, which means that all cells that exist in both Hamiltonians will be substituted.
                     Mind that the cell coordinates have to be lists, not tuples!
        mixin_assoc: Association list for orbitals in the current Hamiltonian and the mixin Hamiltonian. Type is dictionary.
                     If the mixin Hamiltonian describes a different system, the orbital numbers may not be the same.
                     Only the relevant orbitals (those mentioned in mixin_hoppings) have to be here.
                     Default is None, which means that the orbital numbers are assumed to be identical.
                     Example:    Main Hamiltonian     Mixin Hamiltonian
                                 0                    0
                                 1                    1
                                 2                    2
                                 3                    3
                                 4                    4
                                 100                  15
                                 101                  16
                                 102                  17
                                 103                  18
                                 104                  19
                                 
                                 mixin_assoc={0:0,1:1,2:2,3:3,4:4,100:15,101:16,102:17,103:18,104:19}
        onsite_potential: List of numbers. The values will be added to the 
        diagonal (=onsite) matrix elements of the main cell. This approximates
        an electrostatic potential in the system. Default is None.                         
        
        output_maincell_only: If True, only the main cell matrix block will be
        calculated. This makes sense for a big system of which you want to
        calculate the eigenvalues, not the bandstructure. Default is false
        
        Return:
        New Hamiltonian with the new properties.
        """
                
        #TODO: Naming (numbers,positions,coordinates) is ambiguous

        oldunitcellmatrixblocks=self.__unitcellmatrixblocks
        oldunitcellnumbers=self.__unitcellnumbers
        oldorbitalpositions=numpy.array(self.__orbitalpositions,copy=False)
        oldorbitalspreads=self.__orbitalspreads #Must be List, not numpy array!
        
        if usedhoppingcells == 'all':
            usedunitcellnrs=range(len(self.__unitcellnumbers))
        else:
            usedunitcellnrs=self.__unitcellcoordinates_to_nrs(usedhoppingcells)
        
        
        nr_unitcells_in_supercell=len(cellcoordinates)   
        
        cellcoordinates_reverse_dict={}
        for i,coord in enumerate(cellcoordinates):
            cellcoordinates_reverse_dict[tuple(coord)]=i
        
        unitcellmatrixblocks_dryctr=[]
        unitcellnumbers=[]
        
        if usedorbitals=='all':
            orbitalnrs=range(self.__nrbands)
        else:
            orbitalnrs=usedorbitals
            
        orbitals_per_unitcell=len(orbitalnrs)
        
        #Set new orbital positions and spreads
        oldunitcellcoordinates=self.unitcellcoordinates(cellcoordinates)
        orbitalspreads=[oldorbitalspreads[i] for i in orbitalnrs]*nr_unitcells_in_supercell #Repeat oldorbitalspreads
        #print oldunitcellcoordinates
        #print oldorbitalpositions
        orbitalpositions=[list(oldorbitalpositions[orb]+cell) for cell in oldunitcellcoordinates for orb in orbitalnrs]
        
        metric_numerator,metric_denominator=self.__metric(latticevecs)
        latticevecs_dot_metric_numerator=numpy.dot(latticevecs,metric_numerator)
        #Loop over cells in supercell
        
        """
        Besser: zuerst alle indizes/positionen aufstellen, dann mit sparse.bmat die matrix zusammenbauen.
        Andere fkten auch aktualisieren!!
        
        ...und auch mal mixins und connections zw. bauteilen (kleben) verbessern. vl wie elektrostatik-kleben?
        """
        for cellnr,cell in enumerate(numpy.array(cellcoordinates)):
            #Loop over old blocks
            for i,oldnumber in zip(range(len(oldunitcellmatrixblocks)),numpy.array(oldunitcellnumbers)):
                if i in usedunitcellnrs:                        
                    hopto=cell+oldnumber
                    
                    hopto_scaled_times_metric_denominator=numpy.dot(latticevecs_dot_metric_numerator,hopto)
                    hopto_scaled=list(hopto_scaled_times_metric_denominator/metric_denominator)
                    hopto_rest_times_metric_denominator=hopto_scaled_times_metric_denominator%metric_denominator
                    hopto_nr=tuple(numpy.dot(hopto_rest_times_metric_denominator,latticevecs)/metric_denominator)
                    
                    try:
                        skip_block=False
                        hopto_nr_index=cellcoordinates_reverse_dict[hopto_nr]#cellcoordinates.index(hopto_nr) 
                    except ValueError:
                        skip_block=True #if the cell to hop to is not in the cellcoordinates list, the block is skipped
                        
                    if output_maincell_only and hopto_scaled!=[0,0,0]:
                        skip_block=True
                    
                    if skip_block==False:                        
                        try:
                            unitcellindex=unitcellnumbers.index(hopto_scaled)
                        except ValueError:
                            unitcellindex=len(unitcellnumbers)
                            unitcellnumbers.append(hopto_scaled)
                            unitcellmatrixblocks_dryctr.append([])
                        
                        #unitcellmatrixblocks[unitcellindex][cellnr*orbitals_per_unitcell:(cellnr+1)*orbitals_per_unitcell,
                        #                                    hopto_nr_index*orbitals_per_unitcell:(hopto_nr_index+1)*orbitals_per_unitcell]=oldblock_selectedorbitals
                        unitcellmatrixblocks_dryctr[unitcellindex].append([i,cellnr,hopto_nr_index])
        
        oldlatticevecs=self.__latticevecs.latticevecs()
        newlatticevecs=numpy.dot(numpy.array(latticevecs),oldlatticevecs) # (A.B)'=B'.A' - new latticevectors in real coordinates
                        
        
        if usedorbitals=='all':
            oldblocks_selectedorbitals=oldunitcellmatrixblocks
        else:
            #the conversion to csr is annoying, but necessary
            #oldblocks_selectedorbitals=[block.tocsr()[numpy.array(orbitalnrs)[:,numpy.newaxis],numpy.array(orbitalnrs)] for block in oldunitcellmatrixblocks]
            oldblocks_selectedorbitals=[block.tocsr()[orbitalnrs,:][:,orbitalnrs] for block in oldunitcellmatrixblocks]
        
        unitcellmatrixblocks_sparse=[]
        emptyblock=sparse.coo_matrix((orbitals_per_unitcell,orbitals_per_unitcell)) #placeholder for empty blocks; coo is much faster than lil. Better understanding may lead to improvements
        for i,cell in enumerate(unitcellmatrixblocks_dryctr):
            unitcellmatrixblocks_sparse_template= [ [ emptyblock if i==j else None for i in range(nr_unitcells_in_supercell) ] for j in range(nr_unitcells_in_supercell) ]
            for block,i,j in cell:
                unitcellmatrixblocks_sparse_template[i][j]=oldblocks_selectedorbitals[block]
            unitcellmatrixblocks_sparse.append(sparse.bmat(unitcellmatrixblocks_sparse_template))
           
           
        #Mix in matrix elements from other hamiltonian
        if mixin_ham!=None:
            #The unitcellmatrixblocks of the mixin_ham will be partly converted to lil_matrix. Not so nice.
            othermatrixblocks=mixin_ham._Hamiltonian__unitcellmatrixblocks
            otherunitcellnumbers=mixin_ham.unitcellnumbers()
            
            myhoppingelements=mixin_hoppings+[(j,i) for i,j in mixin_hoppings]
            if mixin_assoc==None:
                otherhoppingelements=myhoppingelements
            else:
                otherhoppingelements=[(mixin_assoc[i],mixin_assoc[j]) for i,j in myhoppingelements]
            """    
            for mycellidx,mycellnr in enumerate(unitcellnumbers):
                if mycellnr in otherunitcellnumbers and (mixin_cells==None or mycellnr in mixin_cells):
                    othercellidx=otherunitcellnumbers.index(mycellnr)
                    for (i,j),(k,l) in zip(myhoppingelements,otherhoppingelements):
                        unitcellmatrixblocks[mycellidx][i,j]=othermatrixblocks[othercellidx][k,l]
            """            
            for mycellidx,mycellnr in enumerate(unitcellnumbers):
                if mycellnr in otherunitcellnumbers and (mixin_cells==None or mycellnr in mixin_cells):
                    othercellidx=otherunitcellnumbers.index(mycellnr)
                    unitcellmatrixblocks_sparse[mycellidx] = unitcellmatrixblocks_sparse[mycellidx].tolil() #what if it is already a lil_matrix?
                    othermatrixblocks[othercellidx] = othermatrixblocks[othercellidx].tolil()
                    for (i,j),(k,l) in zip(myhoppingelements,otherhoppingelements):
                        #print 'substitute %i, %i with %i, %i'%(i,j,k,l)
                        unitcellmatrixblocks_sparse[mycellidx][i,j]=othermatrixblocks[othercellidx][k,l]                        
                        

        #Add onsite potential = electrostatic potential
        if onsite_potential != None:
            #XXX: sparse.lil_matrix(numpy.diag(... is a weird construction
            #XXX: the conversion to lil_matrix _may_ be a bottleneck
            #main cell block is converted to lil_matrix!             
            unitcellmatrixblocks_sparse[unitcellnumbers.index([0,0,0])]=unitcellmatrixblocks_sparse[unitcellnumbers.index([0,0,0])].tolil()+sparse.lil_matrix(numpy.diag(onsite_potential))   
                        
        #Shift diagonal elements of main cell hopping block
        if energyshift!=None:        
            #XXX: sparse.lil_matrix(numpy.diag(... is a weird construction
            #main cell block is converted to lil_matrix!             
            unitcellmatrixblocks_sparse[unitcellnumbers.index([0,0,0])]=unitcellmatrixblocks_sparse[unitcellnumbers.index([0,0,0])].tolil()+sparse.lil_matrix(numpy.diag((orbitals_per_unitcell*nr_unitcells_in_supercell)*[energyshift]))
        
    
        #Apply magnetic field
        #distances_in_unit_cell=numpy.array([[x-y for x in numpy.array(orbitalpositions)] for y in numpy.array(orbitalpositions)])
        if magnetic_B!=None:        
            Tesla_conversion_factor=1.602176487/1.0545717*1e-5
            #print Tesla_conversion_factor
            for i,number in enumerate(unitcellnumbers):
                unitcellcoordinates=numpy.dot(number,newlatticevecs)
                othercell_orbitalpositions=[unitcellcoordinates+orb for orb in orbitalpositions]
                #distances=distances_in_unit_cell+unitcellcoordinates #distances[i][j]=Distance from orb i in main cell to orb j in other cell
                #print othercell_orbitalpositions
                if gauge_B=='landau_x':
                    phasematrix=numpy.exp(1j*magnetic_B*Tesla_conversion_factor*numpy.array([[-0.5*(other[0]-main[0])*(other[1]+main[1]) for other in othercell_orbitalpositions] for main in numpy.array(orbitalpositions)]))
                if gauge_B=='landau_y':
                    phasematrix=numpy.exp(1j*magnetic_B*Tesla_conversion_factor*numpy.array([[0.5*(other[1]-main[1])*(other[0]+main[0]) for other in othercell_orbitalpositions] for main in numpy.array(orbitalpositions)]))
                if gauge_B=='symmetric':
                    phasematrix=numpy.exp(1j*magnetic_B*Tesla_conversion_factor*numpy.array([[0.5*((other[1]-main[1])*(other[0]+main[0])-(other[0]-main[0])*(other[1]+main[1])) for other in othercell_orbitalpositions] for main in numpy.array(orbitalpositions)]))
                #XXX: matrices are implicitly converted to numpy arrays. Make phasematrix a sparse matrix.
                unitcellmatrixblocks_sparse[i]=sparse.coo_matrix(unitcellmatrixblocks_sparse[i].multiply(phasematrix))
        if energyshift != None and self.__fermi_energy != None:
            newfermi_energy=self.__fermi_energy+energyshift
        else:
            newfermi_energy=self.__fermi_energy
            
        #unitcellmatrixblocks_csr=[block.tocsr() for block in unitcellmatrixblocks_sparse]
      
        return self.from_raw_data(unitcellmatrixblocks_sparse, unitcellnumbers, newlatticevecs,orbitalspreads,orbitalpositions,newfermi_energy)
        #return unitcellmatrixblocks
    
    def __metric(self,basis):
        """
        Calculates the metric for a given basis using the formula
        Inverse[basis].Inverse[Transpose[basis]].
        
        basis: 3x3 matrix, containing the basis vectors in rows.
        
        Return:        
        metric_numerator: The numerator of the metric (3x3 matrix)
        metric_denominator: The denominator - a scalar because it is identical for all elements.
        
        The metric is 1/metric_denominator * metric_numerator.
        """
        
        b=numpy.array(basis)
        
        metric_denominator=(-b[0,2]*b[1,1]*b[2,0]
                          +b[0,1]*b[1,2]*b[2,0]
                          +b[0,2]*b[1,0]*b[2,1]
                          -b[0,0]*b[1,2]*b[2,1]
                          -b[0,1]*b[1,0]*b[2,2]
                          +b[0,0]*b[1,1]*b[2,2])**2
        
        metric_numerator=[
                            [
                            (-(b[0][2]*b[1][1]) + b[0][1]*b[1][2])**2 + (b[0][2]*b[2][1] - b[0][1]*b[2][2])**2 + (-(b[1][2]*b[2][1]) + b[1][1]*b[2][2])**2,
                            (b[0][2]*b[1][0] - b[0][0]*b[1][2])*(-(b[0][2]*b[1][1]) + b[0][1]*b[1][2]) + (-(b[0][2]*b[2][0]) + b[0][0]*b[2][2])*(b[0][2]*b[2][1] - b[0][1]*b[2][2]) + (b[1][2]*b[2][0] - b[1][0]*b[2][2])*(-(b[1][2]*b[2][1]) + b[1][1]*b[2][2]),
                            (-(b[0][1]*b[1][0]) + b[0][0]*b[1][1])*(-(b[0][2]*b[1][1]) + b[0][1]*b[1][2]) + (b[0][1]*b[2][0] - b[0][0]*b[2][1])*(b[0][2]*b[2][1] - b[0][1]*b[2][2]) + (-(b[1][1]*b[2][0]) + b[1][0]*b[2][1])*(-(b[1][2]*b[2][1]) + b[1][1]*b[2][2])
                            ],[
                            (b[0][2]*b[1][0] - b[0][0]*b[1][2])*(-(b[0][2]*b[1][1]) + b[0][1]*b[1][2]) + (-(b[0][2]*b[2][0]) + b[0][0]*b[2][2])*(b[0][2]*b[2][1] - b[0][1]*b[2][2]) + (b[1][2]*b[2][0] - b[1][0]*b[2][2])*(-(b[1][2]*b[2][1]) + b[1][1]*b[2][2]),
                            (b[0][2]*b[1][0] - b[0][0]*b[1][2])**2 + (-(b[0][2]*b[2][0]) + b[0][0]*b[2][2])**2 + (b[1][2]*b[2][0] - b[1][0]*b[2][2])**2,
                            (-(b[0][1]*b[1][0]) + b[0][0]*b[1][1])*(b[0][2]*b[1][0] - b[0][0]*b[1][2]) + (b[0][1]*b[2][0] - b[0][0]*b[2][1])*(-(b[0][2]*b[2][0]) + b[0][0]*b[2][2]) + (-(b[1][1]*b[2][0]) + b[1][0]*b[2][1])*(b[1][2]*b[2][0] - b[1][0]*b[2][2])
                            ],[
                            (-(b[0][1]*b[1][0]) + b[0][0]*b[1][1])*(-(b[0][2]*b[1][1]) + b[0][1]*b[1][2]) + (b[0][1]*b[2][0] - b[0][0]*b[2][1])*(b[0][2]*b[2][1] - b[0][1]*b[2][2]) + (-(b[1][1]*b[2][0]) + b[1][0]*b[2][1])*(-(b[1][2]*b[2][1]) + b[1][1]*b[2][2]),
                            (-(b[0][1]*b[1][0]) + b[0][0]*b[1][1])*(b[0][2]*b[1][0] - b[0][0]*b[1][2]) + (b[0][1]*b[2][0] - b[0][0]*b[2][1])*(-(b[0][2]*b[2][0]) + b[0][0]*b[2][2]) + (-(b[1][1]*b[2][0]) + b[1][0]*b[2][1])*(b[1][2]*b[2][0] - b[1][0]*b[2][2]),
                            (-(b[0][1]*b[1][0]) + b[0][0]*b[1][1])**2 + (b[0][1]*b[2][0] - b[0][0]*b[2][1])**2 + (-(b[1][1]*b[2][0]) + b[1][0]*b[2][1])**2
                            ]
                            ]
        
        return metric_numerator,metric_denominator   
        
        
        
    
    def __absolute_ceiling(self,x):
        """
        Rounds to the next integer value that has the greater absolute value.
        
        1.5 -> 2
        -1.5 -> -2 
        """
        if x>=0:
            return int(numpy.ceil(x))
        else:
            return int(-numpy.ceil(-x)) 
    
    def create_modified_hamiltonian(self,usedhoppingcells='all',usedorbitals='all',energyshift=None,magnetic_B=None,gauge_B='landau_x',mixin_ham=None,mixin_hoppings=None,mixin_cells=None,mixin_assoc=None,onsite_potential=None):
        """
        Creates a Hamiltonian with dropped orbitals or hopping cells. This is just a wrapper for 
        create_supercell_hamiltonian().
        """
        
        return self.create_supercell_hamiltonian([[0,0,0]], [[1,0,0],[0,1,0],[0,0,1]], usedhoppingcells, usedorbitals,energyshift,magnetic_B,gauge_B,mixin_ham,mixin_hoppings,mixin_cells,mixin_assoc,onsite_potential)

    def apply_electrostatic_potential(self,potential):
        """
        Apply an electrostatic potential to the system and return the new
        Hamiltonian.
        
        potential: a LinearInterpolationNOGrid object. If the object is a 1D/2D
        interpolation, the y and z/z coordinate are not used.
        
        Don't forget to match the unit of length and potential!
        
        Best function yet in OOP.
        
        Very Pythonic: potential can be anything with ().
        """
        
        dim=potential.dim()
        
        points=numpy.array(self.__orbitalpositions)[:,:dim]
        potential=potential.map_function_to_points(points)
        return self.create_modified_hamiltonian(onsite_potential=potential)
        
    def matrixelements(self):
        """
        The matrix elements defining the system.
        
        Do not change unless you know what you are doing!
        
        It is a list of sparse matrices. Every list item contains
        the hopping matrix elements to a specific unit cell, as defined
        by unitcellnumbers(). The first matrix index is the number
        of the orbital in the main cell, the second matrix index is the
        number of the orbital in the other cell.
        """
        
        return self.__unitcellmatrixblocks
        
    def hopping_cell_coordinates(self):
        """
        List of coordinates of the orbitals in all cells where
        there are hopping matrix elements. The order of the cells
        is according to unitcellnumbers().
        """
        unitcellcoordinates = numpy.array(self.unitcellcoordinates())
        orbitalpositions = numpy.array(self.__orbitalpositions)
        
        return numpy.array([[orb+cell for orb in orbitalpositions] for cell in unitcellcoordinates])
        
    
    def shift_fermi_energy_to_zero(self):
        """
        Applies an energy shift so that the new Fermi energy is at 0.
        
        The new Hamiltonian is returned.
        """
        
        return self.create_modified_hamiltonian(energyshift=-self.fermi_energy())
    
    def integergrid3d(self,i,j,k):
        """
        Creates an integer grid with the dimensions i,j,k
        """
    
        return [[ii,jj,kk] for ii in range(i) for jj in range(j) for kk in range(k)]

class BandstructurePlot:
    """
    Combine several bandstructure plots.
    
    Call plot(kpoints,data) for every bandstructure plot.
    Then, call save(filename) to save to a file.
    """
    
#    __stylelist=['b-','g-','r-','c-','m-','y-','k-']
#    __plotcounter=0

    def __init__(self,ax):
        self.ax = ax
        
    def __kpoints_to_pathlength(self,points):       
        """
        points: list of points
        
        Calculates the distance from the first point to each point in the list along the path.
        """
        points=numpy.array(points)
        distances=[0]
        distance=0
        for prev,this in zip(points[:-1],points[1:]):
            distance=numpy.linalg.norm(this-prev)+distance
            distances.append(distance)
        return distances
    
#    def set_aspect_ratio(self,aspect):
#        """
#        Set the aspect ratio. For possible values, see
#        http://matplotlib.sourceforge.net/api/axes_api.html#matplotlib.axes.Axes.set_aspect
#        """
#        ax = pyplot.gca()
#        ax.set_aspect(aspect)
    
#    def set_plot_range(self,**kwargs):
#        """
#        Set the plot range using the kwargs
#        xmin, xmax, ymin, ymax.
#        """
#
#        #http://matplotlib.sourceforge.net/api/pyplot_api.html#matplotlib.pyplot.axis
#        
#        pyplot.figure(self.__myplot.number)
#        pyplot.axis(**kwargs)
        
        #ax = pyplot.gca()
        #ax.set_autoscale_on(False)
        
    
    def plot(self,kpoints,data):
        """
        Add a bandstructure plot to the figure.
        
        kpoints: list of kpoints
        data: list of eigenvalues for each kpoint.
        """
        
#        """
#        At the beginning, the figure is set to __myplot which was set in the constructor
#        to avoid interference between plot functions.
#        http://stackoverflow.com/questions/7986567/matplotlib-how-to-set-the-current-figure/7987462#7987462
#        """

        pathlength=self.__kpoints_to_pathlength(kpoints)
#        if style == 'auto':
#            stylestring=self.__stylelist[self.__plotcounter % len(self.__stylelist)]
#        else:
#            stylestring=style
            
#        self.__plotcounter+=1
        return [self.ax.plot(pathlength,band)[0] for band in data.transpose()]
            
    def plot_fermi_energy(self,fermi_energy):
        return self.ax.axhline(y=fermi_energy,color='r')
        
    def plot_lattice_point_vlines(self,reclatticepoints,reclatticenames=None):
        positions=self.__kpoints_to_pathlength(reclatticepoints)

        if reclatticenames!=None:
            self.ax.set_xticks(positions)
            self.ax.set_xticklabels(reclatticenames)
            
        return [self.ax.axvline(x=x,dashes=(10,10),color='#AAAAAA') for x in positions]
            
    def set_default_axis_labels(self, energy_unit='eV'):
        self.ax.set_xlabel('k-point path')
        self.ax.set_ylabel('Energy ['+ energy_unit+']')

#    def save(self,filename):
#        """
#        Save the figure to a file. The format is determined
#        by the filename.
#        """
#        pyplot.savefig(filename,dpi=(150))
        
#    def reset(self):
#        """
#        Clear the current figure.
#        """
#        pyplot.clf()
        
#    def show(self):
#        pyplot.show()
    

class LocalizedOrbital:
    """
    Base class for a localized orbital.
    """
    def fourier_transform(self):
        pass

class LocalizedOrbitalFromFunction(LocalizedOrbital):
    def __init__(self, fct, latticevecs, startpos, number=None,
                 position=None, spread=None, gridpoints=10, dim2=False, unit_cell_grid=(1,1,1)):
        """
        Describes a localized orbital, given by a function fct.

        You can evaluate the function by using the call operator ().

        The alternative constructor from_xyz_string() creates a function
        from a string using eval().

        fct: function which takes x,y,z as arguments
        gridpoints: default number of gridpoints per dimension if 
        function has to be discretized (e.g. for discrete Fourier transform)
        by function_on_grid().
        dim2: If True, only one gridpoint in z direction at z=0 is evaluated
        when the function has to be discretized.
        unit_cell_grid: number of unit cells per dimension contained in the volume given by latticevecs.

        Usage:
        >>> a=600
        >>> localized_orbital_from_function = w90.LocalizedOrbitalFromFunction(
        ... lambda x, y, z: (numpy.pi/a)**(3./2)*numpy.exp(-a*(x**2+y**2+z**2)),
        ... numpy.eye(3), [-0.5,-0.5,-0.5], gridpoints=50)
        """
        # XXX: orbitals shouldnt know about their latticevecs
        # also, NOInterpolationLattice has it too
        self.__fct = fct
        self.__latticevecs = latticevecs
        self.__startpos = startpos
        self.number = number
        self.position = position
        self.spread = spread
        self.gridpoints = gridpoints
        self.dim2 = dim2
        self.unit_cell_grid = unit_cell_grid

    @classmethod
    def from_xyz_string(cls, fct_string):
        """
        Creates a function from a string using eval().
        """
        self = cls()
        self.fct = lambda x, y, z: eval(fct_string)
        return self
    
    def __call__(self, *args, **kwargs):
        return self.__fct(*args, **kwargs)
    
    def fourier_transform(self, shape=None, axes=None):
        """
        Calculate the Fourier transform of the orbital.
        With the returned FourierTransform object, you get the
        Fourier transform data and convenient utility functions.
        
        shape: shape of the supercell (3-tuple), which is empty except for the
        given data grid, in integer multiples of the data grid size.
        Default is None, which equals (1,1,1). 
        """
        
        data = self.function_on_grid()
        if shape is None:
            cell_shape = data.shape
        else:
            # XXX: error occurs if grid to transform is not a multiple of unit cell grid -> handle        
            cell_shape = [(x * y) / z for x, y, z in zip(shape, data.shape, self.unit_cell_grid)]
                    
        return envtb.utility.fourier.FourierTransform(
            self.latticevecs(), data, cell_shape, axes)
            
    def latticevecs(self):
        return self.__latticevecs
    
    def function_on_grid(self, gridpoints=None, dim2=None):
        """
        Evaluate the function on a grid.

        gridpoints: Grid points per dimension. If None,
        the setting from the constructor is used.
        dim2: If True, only one gridpoint in z direction at z=0 is evaluated.
        """

        if gridpoints is None:
            gridpoints = self.gridpoints
        
        if dim2 is None:
            dim2 = self.dim2
            
        if dim2 is True:
            zrange = [0.]
        else:
            zrange = numpy.arange(0, 1, 1. / gridpoints)

        fct_on_grid = numpy.array([[[
                  self.__call__(*(self.__startpos + numpy.dot([i, j, k], self.__latticevecs)))
                  for k in zrange]
                  for j in numpy.arange(0, 1, 1. / gridpoints)]
                  for i in numpy.arange(0, 1, 1. / gridpoints)])

        return fct_on_grid

# XXX: fully support more than one unit cell contained in the data grid.

class WannierOrbital(utilities.LinearInterpolationNOGrid, LocalizedOrbital):
    def __init__(self, orbgrid, grid_latticevecs, startpos, unit_cell_grid=(1,1,1), number=None, position=None, spread=None):
        """
        Represents a Wannier orbital.
        
        orbgrid: Orbital data
        grid_latticevecs: Grid lattice vectors
        startpos: Starting position of the grid.
        number: Orbital index
        position: Center position
        spread: Orbital spread
        unit_cell_grid: number of unit cells per dimension contained in the data.
        """
        utilities.LinearInterpolationNOGrid.__init__(self,orbgrid, grid_latticevecs,startpos)

        self.position = position
        self.spread = spread
        self.number = number
        self.unit_cell_grid = unit_cell_grid
        
    def set_position(self, position):
        self.position = position
        return self
        
    def set_number(self, number):
        self.number = number
        return self        
        
    def set_spread(self, spread):
        self.spread = spread
        return self
        
    def plot_orbital_3d(self, box, grid, contours):
        """
        Save figure using:
        
        >>> from mayavi import mlab
        >>> mlab.savefig(fname)
        """
        default_orb_value = 0
        def nonetonan(x):
            if x is None:
                return default_orb_value
            else:
                return x
            
        relative_points = numpy.arange(-box,box,grid)
        points=numpy.array([[[self.position+[x,y,z] 
                              for z in relative_points] 
                             for y in relative_points] 
                            for x in relative_points])
        values=[[[nonetonan(self(point)) for point in line] for line in plane] for plane in points]
        
        xv,yv,zv=numpy.mgrid[-box:box:grid,-box:box:grid,-box:box:grid]
        
        mplot=mlab.contour3d(xv,yv,zv,values,contours=contours)
        
        return mplot
        
    def plot_orbital_2d(self, ax, box, grid, drop_axis,mode='imshow'):
            
        default_orb_value = numpy.nan   
        def nonetonan(x):
            if x is None:
                return default_orb_value
            else:
                return x

        relative_points = numpy.arange(-box,box,grid)
        
        if drop_axis == 'z':
            points=numpy.array([[self.position+[x,y,0]  
                                 for y in relative_points] 
                                for x in relative_points])
            extent=[self.position[0]-box,
                    self.position[0]+box,
                    self.position[1]-box,
                    self.position[1]+box
                   ]
        if drop_axis == 'x':
            points=numpy.array([[self.position+[0,y,z]  
                                 for z in relative_points] 
                                for y in relative_points])
            extent=[self.position[1]-box,
                    self.position[1]+box,
                    self.position[2]-box,
                    self.position[2]+box
                   ]                                
        if drop_axis == 'y':
            points=numpy.array([[self.position+[x,0,z]  
                                 for x in relative_points] 
                                for z in relative_points])  
            extent=[self.position[2]-box,
                    self.position[2]+box,
                    self.position[0]-box,
                    self.position[0]+box
                   ]                                                                                              
                                
        values=numpy.array([[nonetonan(self(point)) for point in line] for line in points]).transpose()
        if mode=='imshow':
            im=ax.imshow(values,origin='lower',interpolation='nearest', extent=extent)
        if mode=='contour':
            im=ax.contour(values,[-1,1,2,3,4,5,6,7,8,9,10],extent=extent)
        #cax = fig.add_axes([0.88, 0.3, 0.03, 0.4])
       # pyplot.subplots_adjust(wspace=0,hspace=0,left=0.1,right=0.85,bottom=0.1,top=0.95)

        #cb=pyplot.colorbar(im,orientation='vertical',cax=cax)
        
        return im,points,values
        
    def plot_orbital_1d(self, ax, box, grid, axis):
        default_orb_value = 0    
        def nonetonan(x):
            if x is None:
                return default_orb_value
            else:
                return x

        relative_points = numpy.arange(-box,box,grid)
        
        if axis == 'z':
            points=numpy.array([self.position+[0,0,z]
                                 for z in relative_points])
            abscissa=points[:,2]
        if axis == 'x':
            points=numpy.array([self.position+[x,0,0]  
                                 for x in relative_points])
            abscissa=points[:,0]
        if axis == 'y':
            points=numpy.array([self.position+[0,y,0]  
                                 for y in relative_points])
            abscissa=points[:,1]
                                
        values=[self(point) for point in points]

        
        pl=ax.plot(abscissa,values, label=str(self.number))
        #cax = fig.add_axes([0.88, 0.3, 0.03, 0.4])
       # pyplot.subplots_adjust(wspace=0,hspace=0,left=0.1,right=0.85,bottom=0.1,top=0.95)

        #cb=pyplot.colorbar(im,orientation='vertical',cax=cax)
        
        return pl
    
    def fourier_transform(self, shape=None, axes=None):
        """
        Calculate the Fourier transform of the orbital.
        With the returned FourierTransform object, you get the
        Fourier transform data and convenient utility functions.
        
        shape: shape of the supercell (3-tuple), which is empty except for the
        given data grid, in integer multiples of the data grid size.
        Default is None, which equals (1,1,1).        
        """
        
        if shape is None:
            cell_shape = self.data().shape
        else:
            # XXX: error occurs if grid to transform is not a multiple of unit cell grid -> handle
            cell_shape = [(x * y) / z for x, y, z in zip(shape, self.data().shape, self.unit_cell_grid)]
            
        return envtb.utility.fourier.FourierTransform(
            self.latticevecs(), self.data(), cell_shape, axes)
    

class LocalizedOrbitalSet:
    def __init__(self, orbitals, latticevecs):
        """
        Base class for basis orbital sets. You can also use the base class
        to arrange your own set.
        
        orbitals: dict of orbitals (instance of LocalizedOrbital)
        latticevecs: lattice vectors describing the unit cell.
        """
        self.orbitals = orbitals
        self.latticevecs = latticevecs
        

class WannierRealSpaceOrbitals(LocalizedOrbitalSet):
    """
    Read wannier90_*.xsf files produced by wannier90. After calling read(),
    the orbitals are available as LinearInterpolationNOGrid objects in the
    dictionary orbitals, with the orbital number as key (see example).
    
    The path variable given to the constructor can be a directory or a
    single file.
    
    If a *.wout file exists in the given directory/in the same directory
    as the given single file, the orbital position and spread information
    will be read from there and made available through the properties spreads and 
    positions (if it not exists, those will be None).
    
    Usage:
    >>> xsfpath = '/tmp/mycalc'
    >>> wrso = WannierRealSpaceOrbitals(xsfpath)
    >>> print wrso.xsffiles
    >>> wrso.read()
    >>> for nr,orb in sorted(wrso.orbitals.iteritems()):
    >>>     points=numpy.array([(0,0,z) for z in numpy.arange(-10,10,0.1)])
    >>>     points=numpy.array(orb.filter_points_in_domain_of_definition(points))
    >>>     values=orb.map_function_to_points(points)
    >>>     plot(points[:,2], values,label=str(nr))
    >>> legend()
    """
    def __init__(self, path, unit_cell_grid):
        """
        path: If path points to a directory, all *.xsf files will be read.
              If it points to a file, only this file will be read.
        """
        
        if os.path.isdir(path):
            self.directory = path     
            self.xsffiles=glob.glob(os.path.join(path,'*.xsf'))  
        else:
            self.xsffiles = [path]
            self.directory = os.path.dirname(path)
            
        self.orbitals = None
        self.unit_cell_grid = unit_cell_grid
        
    def read(self):
        """
        Read the given orbital files and *.wout, if it exists.
        """
        self.orbitals = {}
        for xsffile in self.xsffiles:
            print '\rread ',xsffile,
            orbid=int(re.search('wannier90_(.*).xsf',xsffile).groups()[0])
            self.orbitals[orbid] = self.__read_wannier90_orbital_file(xsffile)
            
        woutfiles = glob.glob(os.path.join(self.directory,'*.wout'))
        
        if len(woutfiles) > 0:
            spreads, positions = self.__orbital_spreads_and_positions(woutfiles[0])
                        
            for i,spread,position in zip(range(1,len(spreads)+1),spreads,positions):
                if i in self.orbitals.keys():
                    self.orbitals[i].set_position(numpy.array(position))
                    self.orbitals[i].set_spread(spread)    
                    self.orbitals[i].set_number(i)        
        return self
        
    def __read_wannier90_orbital_file(self,path):
        """
        Read *.xsf file generated using wannier90 into a LinearInterpolationNOGrid.
        """
        
        def string_to_number(s):
            """
            Convert string to number, if possible (float or integer).
            """
            try:
                return int(s)
            except ValueError:
                try:
                    return float(s)
                except ValueError:
                    return s
                    
        def flatten(list2d):
            return [item for sublist in list2d for item in sublist]                    
            
        lines = [[string_to_number(element) for element in line.split()] for line in open(path).readlines()]
        
        start = lines.index(['BEGIN_BLOCK_DATAGRID_3D'])
        shape = numpy.array(lines[start+3])
        nx, ny, nz = shape
        startpos = lines[start+4]
        latticevecs = numpy.array(lines[start+5:start+8])
        
        orbgrid=numpy.transpose(numpy.reshape(numpy.array(flatten(lines[start+8:start+8+int(math.ceil(nx*ny*nz/6.))])),(nz,ny,nx)))
        
        grid_latticevecs = [vec/ctr for vec,ctr in zip(latticevecs,shape)]
        
        return WannierOrbital(orbgrid, grid_latticevecs,startpos, self.unit_cell_grid)
    
    #Copy from Hamiltonian. XXX Refactor!!    
    def __orbital_spreads_and_positions(self,wannier90_wout_filename):
        """
        Reads the final wannier90 orbital spreads and positions from the
        wannier90.wout file.
        
        wannier90_wout_filename: path to the wannier90.wout file.
        
        Return:
        spreads,positions
        """
        
        #TODO: What about performance? Stuff gets copied pretty often
        #maybe use this http://stackoverflow.com/a/4944929/1447622
        
        f = open(wannier90_wout_filename, 'r')
        lines = f.readlines()
        
        splitspaces = [[x.strip(',') for x in line.split()] for line in lines]
        #Catastrophe - only a Flatten[] command, but unreadable
        infile = [list(itertools.chain(*[x.split(',') for x in line])) for line in splitspaces]
        
        for nr,line in enumerate(lines):
            ret = line.find("Number of Wannier Functions")
            if ret >=0:
                break
            
        nrbands=int(infile[nr][6])
        
        start = infile.index(["Final","State"])
        data = infile[start+1:start+nrbands+1]
        
        f.close()
        
        spreads = [float(x[10]) for x in data]
        positions = [[float(x[6][:-1]),float(x[7][:-1]),float(x[8])] for x in data]
        
        return spreads,positions
        
    def print_positions_and_spreads(self):
        for i, orb in self.orbitals.iteritems():
            x,y,z = orb.position
            print 'orbital',i,': position',orb.position, 'spread', orb.spread
            
    def plot_positions(self):
        fig=pyplot.figure()
        ax = fig.add_subplot(1,1,1)
        for i, orb in gnrorbset.orbitals.iteritems():
            x,y,z = orb.position
            ax.text(x,y+0.12,str(i),horizontalalignment='center')
            ax.plot([x], [y], 'r.', markersize=10.0)
            
            
class Wannier90WoutFile:
    def __init__(self,wannier90_wout_filename):
        self.spreads, self.positions = \
            self.__orbital_spreads_and_positions(wannier90_wout_filename)

    #Copy from Hamiltonian. XXX Refactor!!    
    def __orbital_spreads_and_positions(self,wannier90_wout_filename):
        """
        Reads the final wannier90 orbital spreads and positions from the
        wannier90.wout file.
        
        wannier90_wout_filename: path to the wannier90.wout file.
        
        Return:
        spreads,positions
        """
        
        #TODO: What about performance? Stuff gets copied pretty often
        #maybe use this http://stackoverflow.com/a/4944929/1447622
        
        f = open(wannier90_wout_filename, 'r')
        lines = f.readlines()
        
        splitspaces = [[x.strip(',') for x in line.split()] for line in lines]
        #Catastrophe - only a Flatten[] command, but unreadable
        infile = [list(itertools.chain(*[x.split(',') for x in line])) for line in splitspaces]
        
        for nr,line in enumerate(lines):
            ret = line.find("Number of Wannier Functions")
            if ret >=0:
                break
            
        nrbands=int(infile[nr][6])
        
        start = infile.index(["Final","State"])
        data = infile[start+1:start+nrbands+1]
        
        f.close()
        
        spreads = [float(x[10]) for x in data]
        positions = [[float(x[6][:-1]),float(x[7][:-1]),float(x[8])] for x in data]
        
        return spreads,positions
        
    def print_positions_and_spreads(self):
        for i in range(len(self.spreads)):
            print 'orbital',i+1,': position',self.positions[i], 'spread', self.spreads[i]
            
    def plot_positions(self, ax):
        for i in range(len(self.spreads)):
            x,y,z = self.positions[i]
            ax.text(x,y+0.12,str(i),horizontalalignment='center')
            ax.plot([x], [y], 'r.', markersize=10.0)
