import numpy as np


class Bandstructure:
    __tol = 1e-10

    def __init__(self, params, kvectors, energies, states, hamiltonians):
        self.params = params
        self.kvectors = kvectors
        self.energies = energies
        self.states = states
        self.hamiltonians = hamiltonians

    def numBands(self):
        """Get the number of bands"""

        return self.energies.shape[-1]

    def getFlatness(self, band=None, local=False):
        """Returns the flatness ratio (bandgap / bandwidth) for all bands, unless a specific band
        index is given. If local is set to true, the flatness is calculated with the value for the
        gap replaced by a local definition for the minimal gap: min_k(E_2 - E_1), instead of
        min_k(E_2) - max_k(E_1)."""

        nb = self.numBands()

        if nb == 1:
            raise Exception("The flatness ratio is not defined for a single band.")

        if band is None:
            bands = range(nb)
        else:
            bands = [band]

        ratios = []
        for b in bands:
            gaps = []
            enThis = self.energies[..., b]

            if b >= 1:  # not the lowest band
                enBottom = self.energies[..., b - 1]
                if local:
                    gaps.append(np.nanmin(enThis - enBottom))
                else:
                    gaps.append(np.nanmin(enThis) - np.nanmax(enBottom))

            if b < nb - 1:  # not the highest band
                enTop = self.energies[..., b + 1]
                if local:
                    gaps.append(np.nanmin(enTop - enThis))
                else:
                    gaps.append(np.nanmin(enTop) - np.nanmax(enThis))

            minGap = np.nanmin(gaps)
            bandwidth = np.nanmax(self.energies[..., b]) - np.nanmin(self.energies[..., b])
            ratios.append(minGap / bandwidth)

        return np.squeeze(ratios)

    def getBerryFlux(self, band=None):
        """Returns the total Berry flux for all bands, unless a specific band index is given."""

        if self.kvectors is None or self.kvectors.dim != 2:
            raise Exception("Only supports 2D k-space arrays")

        # Derivatives of the Hamiltonian (multiplied by dx, dy)
        Dx = np.empty_like(self.hamiltonians)
        Dx[1:-1, :] = (self.hamiltonians[2:, :] - self.hamiltonians[:-2, :])/2

        Dy = np.empty_like(self.hamiltonians)
        Dy[:, 1:-1] = (self.hamiltonians[:, 2:] - self.hamiltonians[:, :-2])/2

        nb = self.numBands()

        if band is None:
            bands = range(nb)
        else:
            bands = [band]

        fluxes = []
        for n in bands:
            # nth eigenvector
            vecn = self.states[..., n]
            # other eigenvectors
            vecm = self.states[..., np.arange(nb)[np.arange(nb) != n]]

            # nth eigenenergy
            en = self.energies[..., n]
            # other eigenenergies
            em = self.energies[..., np.arange(nb)[np.arange(nb) != n]]
            ediff = (em - en[:, :, None])**2

            # put everything together
            vecnDx = np.sum(vecn.conj()[:, :, :, None] * Dx, axis=-2)
            vecnDxvexm = np.sum(vecnDx[:, :, :, None] * vecm, axis=-2)

            vecnDy = np.sum(vecn.conj()[:, :, :, None] * Dy, axis=-2)
            vecnDyvexm = np.sum(vecnDy[:, :, :, None] * vecm, axis=-2)

            # calculate Berry curvature
            gamma = -2 * np.imag(np.sum((vecnDxvexm/ediff) * vecnDyvexm.conj(), axis=-1))
            gamma[self.kvectors.mask] = 0

            # calculate Berry flux
            fluxes.append(np.sum(gamma))

        return np.squeeze(fluxes)

    def getBerryPhase(self, band=None):
        """Returns the Berry phase along the underlying 1D path for all bands, unless a specific
        band index is given."""

        if self.kvectors is None or self.kvectors.dim != 1:
            raise Exception("Only supports 1D k-space arrays")

        if band is None:
            bands = range(self.numBands())
        else:
            bands = [band]

        phases = []
        for n in bands:
            psi = self.states[..., n]

            # Use a smooth gauge for psi=|u_k> by choosing the first entry of |u_k> to be real
            gauge = np.exp(-1j * np.angle(psi[:, 0]))
            psi = psi * gauge[:, None]

            # Calculate numerical derivative d/dk |u_k> dk
            deriv = np.empty_like(psi)
            deriv[1:-1, :] = (psi[2:]-psi[:-2])/2

            # Compute <u_k| i * d/dk |u_k> dk
            berry = 1j * np.sum(psi.conj() * deriv, axis=1)
            berry[self.kvectors.mask] = 0

            # Integrate over path and save the result
            phases.append(np.sum(berry).real)

        return np.squeeze(phases)

    def plot(self, filename=None, show=True, legend=False, elim=None):
        """Plot the band structure.

        :param filename: Filename of the plot (if it is None, plot will not be saved).
        :param show:     Show the plot in a matplotlib frontend.
        :param legend:   Show a plot legend describing the bands.
        :param elim:     Limits on the "energy" axis.
        """

        import matplotlib.pyplot as plt

        if self.kvectors is None:
            # Zero-dimensional system
            plt.plot(self.energies[0], linewidth=0, marker='+')

        elif self.kvectors.dim == 1:
            for b, energy in enumerate(self.energies.T):
                plt.plot(self.kvectors.pathLength, energy, label=str(b))

            if self.kvectors.specialpoints_idx is not None:
                specialpoints = self.kvectors.pathLength[self.kvectors.specialpoints_idx]
                plt.xticks(specialpoints, self.kvectors.specialpoints_labels)
                plt.xlim(min(specialpoints), max(specialpoints))
                if elim is not None:
                    plt.ylim(elim)

            if legend:
                plt.legend()

        else:
            from mpl_toolkits.mplot3d import Axes3D  # noqa
            from matplotlib import cm
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')

            eMin = np.nanmin(self.energies)
            eMax = np.nanmax(self.energies)

            for band in range(self.energies.shape[-1]):
                energy = self.energies[..., band].copy()
                energy[np.isnan(energy)] = np.nanmin(energy)

                ax.plot_surface(self.kvectors.points_masked[..., 0],
                                self.kvectors.points_masked[..., 1],
                                energy,
                                cstride=1,
                                rstride=1,
                                cmap=cm.cool,
                                vmin=eMin,
                                vmax=eMax,
                                linewidth=0.001,
                                antialiased=True
                                )

                if elim is not None:
                    plt.zlim(elim)

        if filename is not None:
            plt.savefig(filename.format(**self.params))

        if show:
            plt.show()

    def plotState(self, kIndex=0, state=0, orbital=None, filename=None, show=True):
        """Plot the probability density of a specific eigenstate |u(k,nu)>

        :param kIndex:  specifies the momentum ``k = kvectors[kIndex]``
        :param band:    The band (eigenstate) index
        :param orbital: Orbital to project onto. For ``None``, plot all orbitals
        """

        import matplotlib.pyplot as plt

        basis = self.params.get("lattice").getVecsBasis()
        nSubs = basis.shape[0]

        sorter = np.argsort(self.energies[kIndex])

        states = self.states.reshape(self.states.shape[:-2]+(nSubs, -1, self.states.shape[-1])) # k, sub, orb, state
        states = states[kIndex].transpose(2, 0, 1)[sorter] # state, sub, orb
        nOrbs = states.shape[-1]

        energies = self.energies[kIndex][sorter]

        probs = np.abs(states)**2
        phases = np.angle(states)

        # === preparation of the plot ===
        fig, ax1 = plt.subplots()
        ax1.set_aspect('equal')
        ax1.set_title("Eigenstate {} with E={}".format(state, energies[state]))

        ax2=ax1.twinx()
        ax3=ax1.twiny()

        # === plotting ===
        ax1.plot(basis[:,0], basis[:,1], 'x', c='0.7', alpha=1, zorder=-5, ms=8)

        for orbital in range(nOrbs):
            # --- 2d plot ---
            prob = probs[state, :, orbital]
            phase = phases[state, :, orbital]
            color = ['r', 'b', 'g', 'y'][orbital]
            #plt.scatter(basis[:, 0], basis[:, 1], s=prob*2e4, \
            #    c=phase,edgecolor=color, linewidths=3, alpha=0.5)
            ax1.scatter(basis[:,0], basis[:,1], s=prob*2e4, \
                c=color, alpha=0.5)

            # --- projection ---
            sorter = np.argsort(prob)
            prob = prob[sorter]
            pos = basis[sorter]

            splitter =  np.where(np.diff(prob) > self.__tol)[0] + 1
            prob_split = np.split(prob,splitter)
            pos_split = np.split(pos,splitter,axis=0)

            for prob, pos in zip(prob_split,pos_split):
                ax2.plot(pos[:,0], prob, 'x-', c=color,alpha=0.5,ms=8)
                ax3.plot(prob, pos[:,1], 'x-', c=color,alpha=0.5,ms=8)

        ax1.set_xlabel("X-position")
        ax1.set_ylabel("Y-position")

        ax1.grid()

        # === resizing ===
        maxprob = max(ax3.get_xlim()[1],ax2.get_ylim()[1])
        ax3.set_xlim(0,maxprob*15)
        ax2.set_ylim(0,maxprob*15)
        ax3.set_xticks([])
        ax2.set_yticks([])

        x1,x2 = ax1.get_xlim() #min(basis[:,0]), max(basis[:,0])
        ax1.set_xlim(x1-(x2-x1)*(2/6),x2+(x2-x1)/6)
        y1,y2 = ax1.get_ylim() #min(basis[:,1]), max(basis[:,1])
        ax1.set_ylim(y1-(y2-y1)*(2/6),y2+(y2-y1)/6)

        # === output ===
        if filename is not None:
            plt.savefig(filename.format(**self.params))

        if show:
            plt.show()

    def plotRadialdistribution(self, kIndex=0, statemarker=None, filename=None, show=True,kde=False):
        """Plot the radial distribution of states."""

        import matplotlib.pyplot as plt

        basis = self.params.get("lattice").getVecsBasis().copy() # sub, coord
        center = np.sum(basis,axis=0)/basis.shape[0]
        basis -= center # TODO Do the shift inside the lattice class

        radii = np.sqrt(np.sum(basis**2,axis=-1)) # sub

        nSubs = basis.shape[0]

        sorter = np.argsort(self.energies[kIndex])
        states = self.states.reshape(self.states.shape[:-2]+(nSubs, -1, self.states.shape[-1])) # k, sub, orb, state
        states = states[kIndex].transpose(2, 0, 1)[sorter] # state, sub, orb
        probs = np.abs(states)**2 # state, sub, orb

        nOrbs = states.shape[-1]
        nStates = states.shape[0]

        # === preparation of the plot ===
        fig, ax1 = plt.subplots()

        # === plotting ===
        x, step = np.linspace(min(radii),max(radii),100,retstep=True)
        x = x.tolist()
        x = [x[0]-step]+x+[x[-1]+step]

        for s in range(nStates):
            for o in range(nOrbs):
                prob = probs[s,:,o]
                color = ['r', 'b', 'g', 'y'][o]

                y = np.zeros_like(x)
                for p, r in zip(prob, radii): y[np.argmin(np.abs(x-r))] += p

                ax1.fill_between(y+s,x,color=color,alpha=0.5,lw=0.3)

        ax1.set_ylim(x[0],x[-1])
        ax1.set_xlim(0,nStates)

        ax1.set_xlabel("Eigenstate")
        ax1.set_ylabel("Radial distance")

        ax1.grid()

        # === mark eigenstate ===
        if statemarker is not None:
            ax1.set_title("Eigenstate {} marked with a yellow line".format(statemarker))
            ax1.plot(statemarker*np.ones(2),ax1.get_ylim(), 'y-', alpha=1,lw=2,zorder=-5)

        # === output ===
        if filename is not None:
            plt.savefig(filename.format(**self.params))

        if show:
            plt.show()


    def plotSpectrum(self, statemarker=None, filename=None, show=True,kde=False):
        """Plot spectrum and density of states."""

        import matplotlib.pyplot as plt

        energies = np.sort(self.energies.flat)

        if kde:
            from scipy.stats import gaussian_kde
            kernel = gaussian_kde(energies,bw_method=0.03)
            lin = np.linspace(energies[0],energies[-1],300)
            dos = kernel(lin)
        else:
            dos, lin = np.histogram(energies, bins=50, density=True)
            lin = (lin+(lin[1]-lin[0])/2)[:-1]

        # === preparation of the plot ===
        fig, ax1 = plt.subplots()
        ax2=ax1.twiny()

        # === plotting ===
        ax1.plot(energies, 'kx', alpha=1,ms=4)
        ax2.plot(dos, lin, 'k-', alpha=1,ms=4)

        ax1.set_xlabel("Eigenstate")
        ax1.set_ylabel("Energy")

        ax1.grid()

        # === resizing ===
        ax2.set_xlim(0,max(dos)*8)
        ax2.set_xticks([])

        x1,x2 = ax1.get_xlim()
        ax1.set_xlim(x1-(x2-x1)*(1/8+1/6),x2+(x2-x1)/8)

        # === mark eigenstate ===
        if statemarker is not None:
            ax1.set_title("Eigenstate {} marked with a yellow cross".format(statemarker))
            ax1.plot(statemarker*np.ones(2),ax1.get_ylim(), 'y-', alpha=1,lw=2,zorder=-5)
            ax1.plot(ax1.get_xlim(),energies[statemarker]*np.ones(2), 'y-', alpha=1,lw=2,zorder=-5)

        # === output ===
        if filename is not None:
            plt.savefig(filename.format(**self.params))

        if show:
            plt.show()

    def plotBerryCurvature(self, band=0):
        """Plot the Berry curvature of a specific band in the 2D Brillouin zone."""

        pass
