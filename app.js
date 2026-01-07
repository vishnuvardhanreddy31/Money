// Expense Tracker Application
class ExpenseTracker {
    constructor() {
        this.expenses = this.loadExpenses();
        this.currentPeriod = 'today';
        this.init();
    }

    init() {
        // Set today's date as default
        document.getElementById('date').valueAsDate = new Date();

        // Event Listeners
        document.getElementById('expenseForm').addEventListener('submit', (e) => this.handleAddExpense(e));
        document.getElementById('exportBtn').addEventListener('click', () => this.exportData());
        document.getElementById('importBtn').addEventListener('click', () => document.getElementById('importFile').click());
        document.getElementById('importFile').addEventListener('change', (e) => this.importData(e));
        document.getElementById('searchInput').addEventListener('input', (e) => this.filterExpenses());
        document.getElementById('categoryFilter').addEventListener('change', (e) => this.filterExpenses());

        // Time filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handlePeriodChange(e));
        });

        // Initial render
        this.renderExpenses();
        this.updateSummary();
    }

    // Load expenses from localStorage
    loadExpenses() {
        const stored = localStorage.getItem('expenses');
        return stored ? JSON.parse(stored) : [];
    }

    // Save expenses to localStorage
    saveExpenses() {
        localStorage.setItem('expenses', JSON.stringify(this.expenses));
    }

    // Add new expense
    handleAddExpense(e) {
        e.preventDefault();

        const expense = {
            id: Date.now(),
            amount: parseFloat(document.getElementById('amount').value),
            category: document.getElementById('category').value,
            date: document.getElementById('date').value,
            description: document.getElementById('description').value || '',
            createdAt: new Date().toISOString()
        };

        this.expenses.unshift(expense);
        this.saveExpenses();
        this.renderExpenses();
        this.updateSummary();

        // Reset form
        e.target.reset();
        document.getElementById('date').valueAsDate = new Date();

        // Show success feedback
        this.showNotification('Expense added successfully!', 'success');
    }

    // Delete expense
    deleteExpense(id) {
        if (confirm('Are you sure you want to delete this expense?')) {
            this.expenses = this.expenses.filter(exp => exp.id !== id);
            this.saveExpenses();
            this.renderExpenses();
            this.updateSummary();
            this.showNotification('Expense deleted successfully!', 'success');
        }
    }

    // Edit expense
    editExpense(id) {
        const expense = this.expenses.find(exp => exp.id === id);
        if (expense) {
            document.getElementById('amount').value = expense.amount;
            document.getElementById('category').value = expense.category;
            document.getElementById('date').value = expense.date;
            document.getElementById('description').value = expense.description;

            // Delete the old one
            this.expenses = this.expenses.filter(exp => exp.id !== id);
            this.saveExpenses();
            this.renderExpenses();
            this.updateSummary();

            // Scroll to form
            document.getElementById('expenseForm').scrollIntoView({ behavior: 'smooth' });
        }
    }

    // Filter expenses by search and category
    filterExpenses() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const categoryFilter = document.getElementById('categoryFilter').value;

        let filtered = this.expenses;

        // Filter by period
        filtered = this.getExpensesByPeriod(filtered, this.currentPeriod);

        // Filter by search term
        if (searchTerm) {
            filtered = filtered.filter(exp =>
                exp.description.toLowerCase().includes(searchTerm) ||
                exp.category.toLowerCase().includes(searchTerm) ||
                exp.amount.toString().includes(searchTerm)
            );
        }

        // Filter by category
        if (categoryFilter) {
            filtered = filtered.filter(exp => exp.category === categoryFilter);
        }

        this.renderExpenses(filtered);
    }

    // Get expenses by time period
    getExpensesByPeriod(expenses, period) {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

        return expenses.filter(exp => {
            const expenseDate = new Date(exp.date);

            switch (period) {
                case 'today':
                    return expenseDate.toDateString() === today.toDateString();
                
                case 'week':
                    const weekAgo = new Date(today);
                    weekAgo.setDate(weekAgo.getDate() - 7);
                    return expenseDate >= weekAgo;
                
                case 'month':
                    return expenseDate.getMonth() === now.getMonth() &&
                           expenseDate.getFullYear() === now.getFullYear();
                
                case 'year':
                    return expenseDate.getFullYear() === now.getFullYear();
                
                case 'all':
                default:
                    return true;
            }
        });
    }

    // Handle period change
    handlePeriodChange(e) {
        document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
        e.target.classList.add('active');
        this.currentPeriod = e.target.dataset.period;
        this.filterExpenses();
        this.updateSummary();
    }

    // Update summary statistics
    updateSummary() {
        const filtered = this.getExpensesByPeriod(this.expenses, this.currentPeriod);
        
        // Calculate total
        const total = filtered.reduce((sum, exp) => sum + exp.amount, 0);
        document.getElementById('totalAmount').textContent = `₹${total.toFixed(2)}`;
        
        // Update count
        document.getElementById('transactionCount').textContent = filtered.length;

        // Category breakdown
        const categoryTotals = {};
        filtered.forEach(exp => {
            categoryTotals[exp.category] = (categoryTotals[exp.category] || 0) + exp.amount;
        });

        // Sort by amount
        const sortedCategories = Object.entries(categoryTotals)
            .sort((a, b) => b[1] - a[1]);

        // Render category breakdown
        const breakdownHtml = sortedCategories.length > 0
            ? sortedCategories.map(([category, amount]) => `
                <div class="category-item">
                    <span class="category-name">${this.getCategoryIcon(category)} ${this.formatCategoryName(category)}</span>
                    <span class="category-amount">₹${amount.toFixed(2)}</span>
                </div>
            `).join('')
            : '<p style="text-align: center; color: var(--text-secondary);">No expenses in this period</p>';

        document.getElementById('categoryBreakdown').innerHTML = breakdownHtml;
    }

    // Render expenses list
    renderExpenses(expensesToRender = null) {
        const container = document.getElementById('expensesList');
        const expenses = expensesToRender !== null ? expensesToRender : this.getExpensesByPeriod(this.expenses, this.currentPeriod);

        if (expenses.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📊</div>
                    <h3>No expenses found</h3>
                    <p>Start tracking your expenses by adding one above!</p>
                </div>
            `;
            return;
        }

        container.innerHTML = expenses.map(expense => `
            <div class="expense-item">
                <div class="expense-details">
                    <div class="expense-header">
                        <span class="expense-category">${this.getCategoryIcon(expense.category)} ${this.formatCategoryName(expense.category)}</span>
                        <span class="expense-amount">₹${expense.amount.toFixed(2)}</span>
                    </div>
                    ${expense.description ? `<div class="expense-description">${expense.description}</div>` : ''}
                    <div class="expense-date">${this.formatDate(expense.date)}</div>
                </div>
                <div class="expense-actions">
                    <button class="btn btn-secondary" onclick="tracker.editExpense(${expense.id})" title="Edit">✏️</button>
                    <button class="btn btn-danger" onclick="tracker.deleteExpense(${expense.id})" title="Delete">🗑️</button>
                </div>
            </div>
        `).join('');
    }

    // Get category icon
    getCategoryIcon(category) {
        const icons = {
            food: '🍔',
            grocery: '🛒',
            travel: '✈️',
            bike: '🏍️',
            rent: '🏠',
            investments: '📈',
            lending: '💸',
            entertainment: '🎬',
            utilities: '💡',
            health: '🏥',
            shopping: '🛍️',
            education: '📚',
            other: '📦'
        };
        return icons[category] || '📦';
    }

    // Format category name
    formatCategoryName(category) {
        return category.charAt(0).toUpperCase() + category.slice(1);
    }

    // Format date
    formatDate(dateString) {
        const date = new Date(dateString);
        const options = { year: 'numeric', month: 'short', day: 'numeric' };
        return date.toLocaleDateString('en-IN', options);
    }

    // Export data
    exportData() {
        const dataStr = JSON.stringify(this.expenses, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `expenses_${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        URL.revokeObjectURL(url);
        this.showNotification('Data exported successfully!', 'success');
    }

    // Import data
    importData(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const imported = JSON.parse(event.target.result);
                if (Array.isArray(imported)) {
                    // Merge with existing data, avoiding duplicates
                    const existingIds = new Set(this.expenses.map(exp => exp.id));
                    const newExpenses = imported.filter(exp => !existingIds.has(exp.id));
                    
                    this.expenses = [...this.expenses, ...newExpenses];
                    this.expenses.sort((a, b) => new Date(b.date) - new Date(a.date));
                    
                    this.saveExpenses();
                    this.renderExpenses();
                    this.updateSummary();
                    this.showNotification(`Imported ${newExpenses.length} new expenses!`, 'success');
                } else {
                    this.showNotification('Invalid file format!', 'error');
                }
            } catch (error) {
                this.showNotification('Error importing file!', 'error');
                console.error('Import error:', error);
            }
        };
        reader.readAsText(file);
        
        // Reset file input
        e.target.value = '';
    }

    // Show notification
    showNotification(message, type = 'success') {
        // Create notification element
        const notification = document.createElement('div');
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 25px;
            background: ${type === 'success' ? 'var(--primary-color)' : 'var(--danger-color)'};
            color: white;
            border-radius: 8px;
            box-shadow: var(--shadow-lg);
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateX(100%)';
            notification.style.transition = 'all 0.3s';
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }
}

// Initialize the app
const tracker = new ExpenseTracker();
