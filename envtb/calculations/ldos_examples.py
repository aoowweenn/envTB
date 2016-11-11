#! /usr/bin/env python
import envtb.ldos.hamiltonian
import envtb.ldos.potential 
import envtb.ldos.plotter
import envtb.ldos.local_density
import matplotlib.pyplot as plt
import envtb.wannier90.w90hamiltonian as w90hamiltonian
import numpy as np

def electron_density_example(Nx = 20, Ny = 20, mu = 0.5, kT = 0.0025):
    
    ham = envtb.ldos.hamiltonian.HamiltonianTB(Ny, Nx)
    ham2 = ham.make_periodic_y()
    ham3 = ham2.make_periodic_x()
    
    dens = ham3.electron_density(mu, kT)
    
    envtb.ldos.plotter.Plotter(list(range(ham.Ny)), dens[ham.Ny:2*ham.Ny]).plotting()
    plt.show()
    
    envtb.ldos.plotter.Plotter().plot_density(dens, ham.coords)
    
    plt.show()
    
    return None
# end def electron_density_example

def electron_density_graphene_example(Nx=30, Ny=32, mu=0.0, kT=0.0025, magnetic_B=500.0):
    
    ham=envtb.ldos.hamiltonian.HamiltonianGraphene(Ny, Nx)
    #ham2 = ham.make_periodic_x()
    #ham_per = ham.make_periodic_y()
    #ham_per.get_position()
    
    ham2 = ham.apply_magnetic_field(magnetic_B, gauge='landau_x')
    
    dens1 = ham2.electron_density(mu, kT)
    
    envtb.ldos.plotter.Plotter().plot_density(dens1, ham2.coords)
    plt.show()
    
    dens2 = ham2.electron_density(mu+1, kT)
    
    envtb.ldos.plotter.Plotter().plot_density(dens2-dens1, ham2.coords)
    plt.show()
    
    
    return None
# end def electron_density_graphene_example

def plot_ldos_example(Nx=40, Ny=40):
    
    potential = envtb.ldos.potential.Potential1DFromFunction(
        lambda x: - 5. * (Ny/2-x) * 2 / Ny)
    ham = envtb.ldos.hamiltonian.HamiltonianTB(Ny, Nx)
    
    ham2 = ham.apply_potential(potential)
    
    envtb.ldos.plotter.Plotter().plot_potential(ham2, ham)
    plt.axes().set_aspect
    plt.show()
    
    local_dos=envtb.ldos.local_density.LocalDensityOfStates(ham2)
    
    plt.subplot(2,2,1)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.01), ham2.coords)
    plt.title('E = 0.01')
    plt.subplot(2,2,2)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.2), ham2.coords)
    plt.title('E = 0.2')
    plt.subplot(2,2,3)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.5), ham2.coords)
    plt.title('E = 0.5')
    plt.subplot(2,2,4)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(1.0), ham2.coords)
    plt.title('E = 1.0')
    
    plt.show()
    
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.01), ham2.coords)
    plt.axes().set_aspect('equal')
    plt.show()
    
    return None
# end def plot_ldos_example

def plot_ldos_graphene_example(Nx=20, Ny=30, magnetic_B=150.0):
    
    ham_nm = envtb.ldos.hamiltonian.HamiltonianGraphene(Ny, Nx)
    ham = ham_nm.apply_magnetic_field(magnetic_B)
    print(ham.mtot)
    #ham.mtot[0,0] = 10.0
    #ham.mtot[0,1] = 0.0
    #ham.mtot[1,0] = 0.0
    local_dos = envtb.ldos.local_density.LocalDensityOfStates(ham)
    
    #ham.plot_bandstructure()

    plt.subplot(2,2,1)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.0), ham.coords)
    plt.title(r'$E = 0.0$')
    plt.subplot(2,2,2)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.15), ham.coords)
    plt.title(r'$E = 0.15$')
    plt.subplot(2,2,3)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.2), ham.coords)
    plt.title(r'$E = 0.2$')
    plt.subplot(2,2,4)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.3), ham.coords)
    plt.title(r'$E = 0.3$')
    plt.show()
    
    return None

def plot_ldos_graphene_armchair_example(Nx=20, Ny=30, magnetic_B=150.0):
    
    ham_nm = envtb.ldos.hamiltonian.HamiltonianGrapheneArmchair(Ny, Nx)
    ham = ham_nm.apply_magnetic_field(magnetic_B, gauge='landau_y')
    local_dos = envtb.ldos.local_density.LocalDensityOfStates(ham)
    
    #ham.plot_bandstructure()
    
    plt.subplot(2,2,1)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.0), ham.coords)
    plt.title('E = 0.0')
    plt.subplot(2,2,2)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.15), ham.coords)
    plt.title('E = 0.15')
    plt.subplot(2,2,3)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.5), ham.coords)
    plt.title('E = 0.5')
    plt.subplot(2,2,4)
    envtb.ldos.plotter.Plotter().plot_density(local_dos(1.2), ham.coords)
    plt.title('E = 1.2')
    plt.show()
    
    return None
# end def plot_ldos_grephene_example

def plot_ldos_example_2Dpot(Nx=30, Ny=70):
    
    #ham=envtb.ldos.hamiltonian.HamiltonianTB(Ny, Nx)
    ham=envtb.ldos.hamiltonian.HamiltonianGraphene(Ny, Nx)
    
    i0 = ham.Nx / 2
    j0 = ham.Ny / 2
    ic = i0*ham.Ny + j0
    potential = envtb.ldos.potential.Potential2DFromFunction(
        lambda x: 0.01 * (ham.coords[ic][1]-x[1])**2 +
                  0.01 * (ham.coords[ic][0]-x[0])**2)
    
    ham2 = ham.apply_potential(potential)
    print(ham2.mtot)
    
    envtb.ldos.plotter.Plotter().plot_potential(ham2, ham)
    plt.axes().set_aspect
    plt.show()
    #ham.make_periodic_y()
    local_dos=envtb.ldos.local_density.LocalDensityOfStates(ham2)
        
    envtb.ldos.plotter.Plotter().plot_density(local_dos(1.5), ham2.coords)
    plt.axes().set_aspect('equal')
    plt.show()
    
    return None
# end def plot_ldos_example_2Dpot

def define_zigzag_ribbon_w90(nnfile, width, length, magnetic_B=None):
    
    if width%2 == 0:
        unitcells = width/2 + 1
        get_rid_of = 1
    else:
        unitcells = width/2 + 2
        get_rid_of = 3

    #ham = w90hamiltonian.Hamiltonian.from_nth_nn_list(nnfile)
    ham = w90hamiltonian.Hamiltonian.from_file("/home/larisa/envtb-data/data/01_graphene_vasp_wannier90/wannier90_hr.dat",
                                               "/home/larisa/envtb-data/data/01_graphene_vasp_wannier90/POSCAR",
                                               "/home/larisa/envtb-data/data/01_graphene_vasp_wannier90/wannier90.wout",
                                               "/home/larisa/envtb-data/data/01_graphene_vasp_wannier90/OUTCAR")
    
    ham2 = ham.create_supercell_hamiltonian(
        [[0, 0, 0], [1, 0, 0]],
        [[1, -1, 0], [1, 1, 0], [0, 0, 1]],
        usedorbitals=(0, 1))
    
    ham3 = ham2.create_supercell_hamiltonian(
        [[0, i, 0] for i in range(unitcells)], 
        [[1, 0, 0], [0, unitcells, 0], [0, 0, 1]])
    
    ham4 = ham3.create_modified_hamiltonian(
        ham3.drop_dimension_from_cell_list(1),
        usedorbitals=list(range(1, ham3.nrorbitals()-get_rid_of)),
        magnetic_B=magnetic_B)
       
    ham5 = ham4.create_supercell_hamiltonian(
        [[i, 0, 0] for i in range(length)], 
        [[length, 0, 0], [0, 1, 0], [0, 0, 1]],
        output_maincell_only=True)
    
    ham6 = ham5.create_modified_hamiltonian(
        usedorbitals=list(range(1, ham5.nrorbitals()-1)))
    
    path = ham4.point_path([[0.0,0,0],[0.95,0,0]],100)
    ham4.plot_bandstructure(path, '' ,'d')
    data=ham4.bandstructure_data(path,basis='c',usedhoppingcells='all')
    print(data)
    #plt.ylim(0, 0.2)
    #plt.show()
    
    return ham5, ham4
# end def define_zigzag_ribbon_w90 
    
def use_w90_example(Ny=30, Nx=30, magnetic_B=None):
    

    #pypar.finalize()  
    # Ny: number of atoms in slice is 2*(Ny+1)
    ham_w90 = define_zigzag_ribbon_w90(
        "../../exampledata/02_graphene_3rdnn/graphene3rdnnlist.dat", 
        Ny, Nx, magnetic_B=magnetic_B)
    
    ham = envtb.ldos.hamiltonian.HamiltonianFromW90(ham_w90, Nx)
    #print ham.mtot
    """
    i0 = ham.Nx / 2
    j0 = ham.Ny / 2
    ic = (i0 - 1) * ham.Ny + (j0-1)
   
    potential = envtb.ldos.potential.Potential2DFromFunction(
        lambda x: 0.01 * (ham.coords[ic][1] - x[1])**2 + 0.01 * \
                 (ham.coords[ic][0] - x[0])**2)
    
    ham2 = ham.apply_potential(potential)
    envtb.ldos.plotter.Plotter().plot_potential(ham2, ham)
    plt.axes().set_aspect('equal')
    plt.show()
    """
    import pypar
    
    proc = pypar.size()
    myid = pypar.rank()
    node = pypar.get_processor_name()
    print('I am proc %d of %d on node %s' % (myid, proc, node))
    
    local_dos=envtb.ldos.local_density.LocalDensityOfStates(ham)
    
    envtb.ldos.plotter.Plotter().plot_density(local_dos(0.7), ham.coords)
    plt.title('E = 0.7')
    plt.axes().set_aspect('equal')
    plt.show()
    
    return None
# end def use_w90_example

def DOS(Nx=50, Ny=50):
    
    potential = envtb.ldos.potential.Potential1DFromFunction(
        lambda x: - 5. * (Ny/2-x) * 2 / Ny)
    ham = envtb.ldos.hamiltonian.HamiltonianTB(Ny, Nx)
    w,v = ham.eigenvalue_problem()
    plt.plot(w, 'o')
    plt.show()
    ham2 = ham.apply_potential(potential)
    den = envtb.ldos.local_density.DensityOfStates(ham, E=np.arange(0,2,0.01))
    plt.hist(w)
    den.plot_density_of_states()
    plt.show()

def run_examples():
    use_w90_example(magnetic_B=0)
    #plot_ldos_example() 
    #electron_density_example() 
    #electron_density_graphene_example() #check electron density for magnetic field?
    #plot_ldos_graphene_example()
    #plot_ldos_graphene_armchair_example() #all FAIL
    #plot_ldos_example_2Dpot()
    #DOS()
if __name__ == '__main__':
    run_examples()
