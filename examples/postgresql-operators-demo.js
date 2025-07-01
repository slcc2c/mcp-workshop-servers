/**
 * PostgreSQL Query Operators Demo
 * Demonstrates the new MongoDB-style query operators
 */

const examples = {
  // Simple equality (backward compatible)
  simpleEquality: {
    where: { name: 'John', age: 25 },
    description: 'Simple equality - unchanged from original implementation'
  },

  // Greater than or equal
  gte: {
    where: { age: { $gte: 18 } },
    description: 'Find all records where age >= 18'
  },

  // Greater than
  gt: {
    where: { score: { $gt: 90 } },
    description: 'Find all records where score > 90'
  },

  // Less than or equal
  lte: {
    where: { price: { $lte: 100 } },
    description: 'Find all records where price <= 100'
  },

  // Less than
  lt: {
    where: { temperature: { $lt: 32 } },
    description: 'Find all records where temperature < 32'
  },

  // Not equal
  ne: {
    where: { status: { $ne: 'inactive' } },
    description: 'Find all records where status != "inactive"'
  },

  // In array
  in: {
    where: { category: { $in: ['electronics', 'books', 'clothing'] } },
    description: 'Find records where category is in the specified array'
  },

  // Not in array
  nin: {
    where: { role: { $nin: ['admin', 'superuser'] } },
    description: 'Find records where role is not in the specified array'
  },

  // Range query
  range: {
    where: { age: { $gte: 18, $lte: 65 } },
    description: 'Find records where age is between 18 and 65 (inclusive)'
  },

  // Complex query
  complex: {
    where: {
      age: { $gte: 21 },
      score: { $gt: 80, $lt: 100 },
      status: 'active',
      category: { $in: ['premium', 'gold'] }
    },
    description: 'Complex query combining multiple operators'
  },

  // Null handling
  nullCheck: {
    where: { deleted_at: null },
    description: 'Find records where deleted_at IS NULL'
  },

  // Not null
  notNull: {
    where: { email: { $ne: null } },
    description: 'Find records where email IS NOT NULL'
  }
};

// Example usage with PostgreSQL server
console.log('PostgreSQL Query Operators Examples\n');
console.log('These operators can be used with:');
console.log('- postgres_select');
console.log('- postgres_update');
console.log('- postgres_delete\n');

for (const [key, example] of Object.entries(examples)) {
  console.log(`${key}:`);
  console.log(`  Description: ${example.description}`);
  console.log(`  Where clause:`, JSON.stringify(example.where, null, 2));
  console.log('');
}

console.log('Example tool calls:\n');

console.log(`// Select with operators
await server.handleToolCall('postgres_select', {
  table: 'users',
  where: { age: { $gte: 18 }, status: 'active' },
  orderBy: [{ column: 'created_at', direction: 'DESC' }],
  limit: 10
});`);

console.log(`\n// Update with operators
await server.handleToolCall('postgres_update', {
  table: 'products',
  data: { discounted: true },
  where: { price: { $gt: 100 }, category: { $in: ['electronics', 'appliances'] } },
  returning: ['id', 'name', 'price']
});`);

console.log(`\n// Delete with operators
await server.handleToolCall('postgres_delete', {
  table: 'sessions',
  where: { last_activity: { $lt: new Date(Date.now() - 24*60*60*1000) } },
  returning: ['id']
});`);